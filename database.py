import json
import os
import re
import base64
import hashlib
import secrets
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

import mysql.connector
from mysql.connector import Error


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _config(include_database: bool = True) -> Dict[str, Any]:
    config: Dict[str, Any] = {
        "host": _env("MYSQL_HOST", "127.0.0.1"),
        "port": int(_env("MYSQL_PORT", "3306")),
        "user": _env("MYSQL_USER", "root"),
        "password": _env("MYSQL_PASSWORD", ""),
        "charset": "utf8mb4",
        "use_unicode": True,
    }
    if include_database:
        config["database"] = _env("MYSQL_DATABASE", "ielts_learning")
    return config


def is_mysql_configured() -> bool:
    return _env("MYSQL_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


@contextmanager
def mysql_connection(use_database: bool = True) -> Iterator[mysql.connector.MySQLConnection]:
    connection = mysql.connector.connect(**_config(include_database=use_database))
    try:
        yield connection
    finally:
        connection.close()


def initialize_database() -> bool:
    if not is_mysql_configured():
        return False

    database_name = _env("MYSQL_DATABASE", "ielts_learning")
    if not re.fullmatch(r"[A-Za-z0-9_]+", database_name):
        raise ValueError("MYSQL_DATABASE 只能包含字母、数字和下划线")

    with mysql_connection(use_database=False) as connection:
        cursor = connection.cursor()
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
            "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        connection.commit()
        cursor.close()

    with mysql_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id VARCHAR(64) PRIMARY KEY,
                password_hash VARCHAR(255) NULL,
                full_name VARCHAR(100) NULL,
                email VARCHAR(160) NULL,
                dashscope_api_key TEXT NULL,
                ai_provider VARCHAR(32) NOT NULL DEFAULT 'tongyi',
                ai_model VARCHAR(128) NULL,
                ai_base_url VARCHAR(255) NULL,
                ai_api_keys JSON NULL,
                current_level DECIMAL(3,1) NOT NULL DEFAULT 5.0,
                listening_level DECIMAL(3,1) NOT NULL DEFAULT 5.0,
                speaking_level DECIMAL(3,1) NOT NULL DEFAULT 5.0,
                reading_level DECIMAL(3,1) NOT NULL DEFAULT 5.0,
                writing_level DECIMAL(3,1) NOT NULL DEFAULT 5.0,
                target_score DECIMAL(3,1) NOT NULL DEFAULT 6.5,
                learning_goal TEXT NULL,
                weak_areas JSON NULL,
                study_time INT NOT NULL DEFAULT 10,
                exam_date DATE NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        _ensure_column(cursor, database_name, "users", "password_hash", "VARCHAR(255) NULL")
        _ensure_column(cursor, database_name, "users", "full_name", "VARCHAR(100) NULL")
        _ensure_column(cursor, database_name, "users", "email", "VARCHAR(160) NULL")
        _ensure_column(cursor, database_name, "users", "dashscope_api_key", "TEXT NULL")
        _ensure_column(cursor, database_name, "users", "ai_provider", "VARCHAR(32) NOT NULL DEFAULT 'tongyi'")
        _ensure_column(cursor, database_name, "users", "ai_model", "VARCHAR(128) NULL")
        _ensure_column(cursor, database_name, "users", "ai_base_url", "VARCHAR(255) NULL")
        _ensure_column(cursor, database_name, "users", "ai_api_keys", "JSON NULL")
        _ensure_column(cursor, database_name, "users", "listening_level", "DECIMAL(3,1) NOT NULL DEFAULT 5.0")
        _ensure_column(cursor, database_name, "users", "speaking_level", "DECIMAL(3,1) NOT NULL DEFAULT 5.0")
        _ensure_column(cursor, database_name, "users", "reading_level", "DECIMAL(3,1) NOT NULL DEFAULT 5.0")
        _ensure_column(cursor, database_name, "users", "writing_level", "DECIMAL(3,1) NOT NULL DEFAULT 5.0")
        _ensure_column(cursor, database_name, "users", "learning_goal", "TEXT NULL")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS study_progress (
                id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL,
                activity VARCHAR(128) NOT NULL,
                score DECIMAL(3,1) NULL,
                data JSON NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_created_at (user_id, created_at),
                INDEX idx_activity (activity),
                CONSTRAINT fk_study_progress_user
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS vocab_progress (
                user_id VARCHAR(64) NOT NULL,
                word VARCHAR(64) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'learning',
                review_count INT NOT NULL DEFAULT 0,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, word),
                CONSTRAINT fk_vocab_progress_user
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_vocabulary (
                id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL,
                word VARCHAR(128) NOT NULL,
                translation TEXT NULL,
                usage_note TEXT NULL,
                source VARCHAR(128) NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_user_word (user_id, word),
                CONSTRAINT fk_user_vocabulary_user
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        connection.commit()
        cursor.close()

    return True


def _ensure_column(cursor, database_name: str, table_name: str, column_name: str, column_definition: str) -> None:
    cursor.execute(
        """
        SELECT COUNT(*) AS column_count
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """,
        (database_name, table_name, column_name),
    )
    column_count = cursor.fetchone()[0]
    if column_count == 0:
        cursor.execute(f"ALTER TABLE `{table_name}` ADD COLUMN `{column_name}` {column_definition}")


def get_database_status() -> Dict[str, Any]:
    if not is_mysql_configured():
        return {"enabled": False, "connected": False, "message": "未启用 MySQL，当前使用内存存储"}

    try:
        initialize_database()
        return {
            "enabled": True,
            "connected": True,
            "message": f"MySQL 已连接：{_config().get('host')}:{_config().get('port')}/{_config().get('database')}",
        }
    except (Error, ValueError) as exc:
        return {"enabled": True, "connected": False, "message": f"MySQL 连接失败：{exc}"}


def ensure_user(user_id: str, profile: Optional[Dict[str, Any]] = None) -> None:
    profile = profile or {}
    weak_areas = profile.get("weak_areas", ["口语", "写作"])
    exam_date = profile.get("exam_date") or None
    current_level = _profile_current_level(profile)

    with mysql_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO users (
                user_id, current_level, listening_level, speaking_level, reading_level,
                writing_level, target_score, weak_areas, study_time, exam_date
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                user_id = VALUES(user_id)
            """,
            (
                user_id,
                current_level,
                float(profile.get("listening_level", current_level)),
                float(profile.get("speaking_level", current_level)),
                float(profile.get("reading_level", current_level)),
                float(profile.get("writing_level", current_level)),
                _round_to_ielts_band(profile.get("target_score", 6.5)),
                json.dumps(weak_areas, ensure_ascii=False),
                int(profile.get("study_time", 10)),
                exam_date,
            ),
        )
        connection.commit()
        cursor.close()


def _profile_current_level(profile: Dict[str, Any]) -> float:
    fallback = float(profile.get("current_level", 5.0))
    levels = [
        float(profile.get("listening_level", fallback)),
        float(profile.get("speaking_level", fallback)),
        float(profile.get("reading_level", fallback)),
        float(profile.get("writing_level", fallback)),
    ]
    return _round_to_ielts_band(sum(levels) / len(levels))


def _round_to_ielts_band(score: float) -> float:
    score = max(0.0, min(9.0, float(score)))
    whole = int(score)
    decimal = score - whole
    if decimal < 0.25:
        return float(whole)
    if decimal < 0.75:
        return whole + 0.5
    return min(9.0, whole + 1.0)


def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return (
        base64.b64encode(salt).decode("ascii")
        + "$"
        + base64.b64encode(digest).decode("ascii")
    )


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_text, digest_text = stored_hash.split("$", 1)
        salt = base64.b64decode(salt_text.encode("ascii"))
        expected = base64.b64decode(digest_text.encode("ascii"))
        actual_text = _hash_password(password, salt).split("$", 1)[1]
        actual = base64.b64decode(actual_text.encode("ascii"))
        return secrets.compare_digest(actual, expected)
    except Exception:
        return False


def authenticate_user(user_id: str, password: str) -> bool:
    initialize_database()

    with mysql_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT password_hash FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        cursor.close()

    if not row:
        return False

    stored_hash = row.get("password_hash")

    if not stored_hash:
        return False

    return _verify_password(password, stored_hash)


def user_exists(user_id: str) -> bool:
    initialize_database()

    with mysql_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE user_id = %s", (user_id,))
        count = cursor.fetchone()[0]
        cursor.close()

    return count > 0


def register_user(user_id: str, password: str, profile: Optional[Dict[str, Any]] = None) -> bool:
    initialize_database()

    if user_exists(user_id):
        return False

    profile = profile or {}
    weak_areas = profile.get("weak_areas", ["口语", "写作"])

    with mysql_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO users (
                user_id, password_hash, current_level, listening_level, speaking_level,
                reading_level, writing_level, target_score, weak_areas, study_time, exam_date
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                _hash_password(password),
                _profile_current_level(profile),
                float(profile.get("listening_level", profile.get("current_level", 5.0))),
                float(profile.get("speaking_level", profile.get("current_level", 5.0))),
                float(profile.get("reading_level", profile.get("current_level", 5.0))),
                float(profile.get("writing_level", profile.get("current_level", 5.0))),
                _round_to_ielts_band(profile.get("target_score", 6.5)),
                json.dumps(weak_areas, ensure_ascii=False),
                int(profile.get("study_time", 10)),
                profile.get("exam_date") or None,
            ),
        )
        connection.commit()
        cursor.close()

    return True


def save_user_api_key(user_id: str, api_key: str) -> None:
    save_user_ai_config(user_id, "tongyi", api_key, "qwen-turbo", "")


def load_user_api_key(user_id: str) -> str:
    config = load_user_ai_config(user_id)
    if config.get("provider") == "tongyi":
        return config.get("api_key", "")

    return ""


def save_user_ai_config(
    user_id: str,
    provider: str,
    api_key: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> None:
    ensure_user(user_id)
    provider = (provider or "tongyi").lower()
    existing_config = load_user_ai_config(user_id)
    api_keys = existing_config.get("api_keys", {})
    if api_key:
        api_keys[provider] = api_key

    dashscope_api_key = api_keys.get("tongyi", "")

    with mysql_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE users
            SET ai_provider = %s,
                ai_model = %s,
                ai_base_url = %s,
                ai_api_keys = %s,
                dashscope_api_key = %s
            WHERE user_id = %s
            """,
            (
                provider,
                model or "",
                base_url or "",
                json.dumps(api_keys, ensure_ascii=False),
                dashscope_api_key,
                user_id,
            ),
        )
        connection.commit()
        cursor.close()


def load_user_ai_config(user_id: str) -> Dict[str, Any]:
    with mysql_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT dashscope_api_key, ai_provider, ai_model, ai_base_url, ai_api_keys
            FROM users
            WHERE user_id = %s
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        cursor.close()

    if not row:
        return {
            "provider": "tongyi",
            "api_key": "",
            "model": "qwen-turbo",
            "base_url": "",
            "api_keys": {},
        }

    api_keys = row.get("ai_api_keys") or {}
    if isinstance(api_keys, str):
        try:
            api_keys = json.loads(api_keys)
        except json.JSONDecodeError:
            api_keys = {}

    legacy_key = row.get("dashscope_api_key") or ""
    if legacy_key and "tongyi" not in api_keys:
        api_keys["tongyi"] = legacy_key

    provider = (row.get("ai_provider") or "tongyi").lower()
    model = row.get("ai_model") or _default_model(provider)
    base_url = row.get("ai_base_url") or _default_base_url(provider)

    return {
        "provider": provider,
        "api_key": api_keys.get(provider, ""),
        "model": model,
        "base_url": base_url,
        "api_keys": api_keys,
    }


def _default_model(provider: str) -> str:
    defaults = {
        "tongyi": "qwen-turbo",
        "deepseek": "deepseek-chat",
        "openai": "gpt-4o-mini",
        "custom": "gpt-4o-mini",
    }
    return defaults.get((provider or "tongyi").lower(), "qwen-turbo")


def _default_base_url(provider: str) -> str:
    defaults = {
        "deepseek": "https://api.deepseek.com",
    }
    return defaults.get((provider or "").lower(), "")


def save_user_profile(user_id: str, profile: Dict[str, Any]) -> None:
    ensure_user(user_id, profile)
    current_level = _profile_current_level(profile)

    with mysql_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE users
            SET full_name = %s,
                email = %s,
                current_level = %s,
                listening_level = %s,
                speaking_level = %s,
                reading_level = %s,
                writing_level = %s,
                target_score = %s,
                learning_goal = %s,
                weak_areas = %s,
                study_time = %s,
                exam_date = %s
            WHERE user_id = %s
            """,
            (
                profile.get("full_name", ""),
                profile.get("email", ""),
                current_level,
                float(profile.get("listening_level", current_level)),
                float(profile.get("speaking_level", current_level)),
                float(profile.get("reading_level", current_level)),
                float(profile.get("writing_level", current_level)),
                _round_to_ielts_band(profile.get("target_score", 6.5)),
                profile.get("learning_goal", ""),
                json.dumps(profile.get("weak_areas", []), ensure_ascii=False),
                int(profile.get("study_time", 10)),
                profile.get("exam_date") or None,
                user_id,
            ),
        )
        connection.commit()
        cursor.close()


def load_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    with mysql_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        cursor.close()

    if not row:
        return None

    weak_areas = row.get("weak_areas")
    if isinstance(weak_areas, str):
        weak_areas = json.loads(weak_areas)

    exam_date = row.get("exam_date")
    if exam_date:
        exam_date = exam_date.strftime("%Y-%m-%d")

    return {
        "user_id": row["user_id"],
        "full_name": row.get("full_name") or "",
        "email": row.get("email") or "",
        "current_level": _round_to_ielts_band(row["current_level"]),
        "listening_level": _round_to_ielts_band(row.get("listening_level", row["current_level"])),
        "speaking_level": _round_to_ielts_band(row.get("speaking_level", row["current_level"])),
        "reading_level": _round_to_ielts_band(row.get("reading_level", row["current_level"])),
        "writing_level": _round_to_ielts_band(row.get("writing_level", row["current_level"])),
        "target_score": _round_to_ielts_band(row["target_score"]),
        "learning_goal": row.get("learning_goal") or "",
        "weak_areas": weak_areas or [],
        "study_time": int(row["study_time"]),
        "exam_date": exam_date or "",
    }


def save_progress(user_id: str, activity: str, data: Dict[str, Any]) -> None:
    ensure_user(user_id)
    score = data.get("score")

    with mysql_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO study_progress (user_id, activity, score, data)
            VALUES (%s, %s, %s, %s)
            """,
            (
                user_id,
                activity,
                float(score) if score is not None else None,
                json.dumps(data, ensure_ascii=False),
            ),
        )
        connection.commit()
        cursor.close()


def get_progress(user_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    with mysql_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, user_id, activity, score, data, created_at
            FROM study_progress
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        rows = cursor.fetchall()
        cursor.close()

    records: List[Dict[str, Any]] = []
    for row in reversed(rows):
        data = row["data"]
        if isinstance(data, str):
            data = json.loads(data)

        timestamp = row["created_at"]
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()

        records.append(
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "timestamp": timestamp,
                "activity": row["activity"],
                "score": float(row["score"]) if row.get("score") is not None else None,
                "data": data,
            }
        )

    return records


def _progress_row_to_record(row: Dict[str, Any]) -> Dict[str, Any]:
    data = row["data"]
    if isinstance(data, str):
        data = json.loads(data)

    timestamp = row["created_at"]
    if isinstance(timestamp, datetime):
        timestamp = timestamp.isoformat()

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "timestamp": timestamp,
        "activity": row["activity"],
        "score": float(row["score"]) if row.get("score") is not None else None,
        "data": data,
    }


def list_users() -> List[Dict[str, Any]]:
    with mysql_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                u.user_id, u.full_name, u.email, u.current_level, u.target_score,
                u.created_at, u.updated_at, COUNT(sp.id) AS record_count
            FROM users u
            LEFT JOIN study_progress sp ON sp.user_id = u.user_id
            GROUP BY u.user_id, u.full_name, u.email, u.current_level, u.target_score, u.created_at, u.updated_at
            ORDER BY u.created_at DESC
            """
        )
        rows = cursor.fetchall()
        cursor.close()

    users = []
    for row in rows:
        users.append({
            "user_id": row["user_id"],
            "full_name": row.get("full_name") or "",
            "email": row.get("email") or "",
            "current_level": _round_to_ielts_band(row.get("current_level", 5.0)),
            "target_score": _round_to_ielts_band(row.get("target_score", 6.5)),
            "record_count": int(row.get("record_count") or 0),
            "created_at": row["created_at"].isoformat() if isinstance(row.get("created_at"), datetime) else str(row.get("created_at") or ""),
            "updated_at": row["updated_at"].isoformat() if isinstance(row.get("updated_at"), datetime) else str(row.get("updated_at") or ""),
        })
    return users


def get_all_progress(limit: int = 500, user_id: str = "") -> List[Dict[str, Any]]:
    with mysql_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        if user_id:
            cursor.execute(
                """
                SELECT id, user_id, activity, score, data, created_at
                FROM study_progress
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
        else:
            cursor.execute(
                """
                SELECT id, user_id, activity, score, data, created_at
                FROM study_progress
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
        rows = cursor.fetchall()
        cursor.close()
    return [_progress_row_to_record(row) for row in rows]


def delete_progress_record_by_id(record_id: int, user_id: str = "") -> bool:
    with mysql_connection() as connection:
        cursor = connection.cursor()
        if user_id:
            cursor.execute(
                "DELETE FROM study_progress WHERE id = %s AND user_id = %s",
                (record_id, user_id),
            )
        else:
            cursor.execute("DELETE FROM study_progress WHERE id = %s", (record_id,))
        connection.commit()
        affected = cursor.rowcount
        cursor.close()
        return affected > 0


def delete_user(user_id: str) -> bool:
    with mysql_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        connection.commit()
        affected = cursor.rowcount
        cursor.close()
        return affected > 0


def delete_progress_record(user_id: str, timestamp: str) -> bool:
    with mysql_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "DELETE FROM study_progress WHERE user_id = %s AND created_at = %s",
            (user_id, timestamp),
        )
        connection.commit()
        affected = cursor.rowcount
        cursor.close()
        return affected > 0


def get_vocab_progress(user_id: str) -> Dict[str, Dict[str, Any]]:
    with mysql_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT word, status, review_count, updated_at
            FROM vocab_progress
            WHERE user_id = %s
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
        cursor.close()

    result: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        updated_at = row.get("updated_at")
        if isinstance(updated_at, datetime):
            updated_at = updated_at.isoformat()
        result[row["word"]] = {
            "status": row["status"],
            "review_count": row["review_count"],
            "updated_at": updated_at,
        }
    return result


def save_vocab_progress(user_id: str, word: str, status: str = "learned") -> None:
    ensure_user(user_id)

    with mysql_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO vocab_progress (user_id, word, status, review_count)
            VALUES (%s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE
                status = VALUES(status),
                review_count = review_count + 1
            """,
            (user_id, word, status),
        )
        connection.commit()
        cursor.close()


def save_user_word(user_id: str, word: str, translation: str = "", usage_note: str = "", source: str = "") -> None:
    ensure_user(user_id)

    with mysql_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO user_vocabulary (user_id, word, translation, usage_note, source)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                translation = VALUES(translation),
                usage_note = VALUES(usage_note),
                source = VALUES(source)
            """,
            (user_id, word, translation, usage_note, source),
        )
        connection.commit()
        cursor.close()


def get_user_words(user_id: str) -> List[Dict[str, Any]]:
    with mysql_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT word, translation, usage_note, source, created_at
            FROM user_vocabulary
            WHERE user_id = %s
            ORDER BY updated_at DESC
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
        cursor.close()

    for row in rows:
        created_at = row.get("created_at")
        if isinstance(created_at, datetime):
            row["created_at"] = created_at.isoformat()
    return rows
