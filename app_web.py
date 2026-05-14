import hmac
import hashlib
import json
import os
import random
import uuid
from functools import wraps
from urllib.parse import urlsplit, urlunsplit
import ipaddress

from flask import Flask, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from markupsafe import Markup, escape

from database import (
    authenticate_user,
    delete_progress_record_by_id,
    delete_progress_record,
    delete_user,
    get_all_progress,
    get_database_status,
    get_progress,
    get_user_words,
    get_vocab_progress,
    initialize_database,
    list_users,
    load_user_ai_config,
    load_user_profile,
    register_user,
    save_progress,
    save_user_ai_config,
    save_user_ai_config_map,
    save_user_profile,
    save_user_word,
    save_vocab_progress,
    set_user_admin,
    update_user_password,
    user_is_admin,
)
from agents import TongyiIELTSAssistant
from ielts_vocab import IELTS_WORDS
from utils import (
    build_task1_chart_assets as _build_task1_chart_assets,
    cross_login_token as _cross_login_token,
    learning_record_title,
    parse_generated_topic_md,
    parse_model_output,
    simple_md_filter as _simple_md_filter,
    verify_cross_token as _verify_cross_token,
)


os.environ.setdefault("MYSQL_ENABLED", "true")
os.environ.setdefault("MYSQL_HOST", "127.0.0.1")
os.environ.setdefault("MYSQL_PORT", "3306")
os.environ.setdefault("MYSQL_USER", "ielts")
os.environ.setdefault("MYSQL_PASSWORD", "ielts")
os.environ.setdefault("MYSQL_DATABASE", "ielts_learning")


AI_PROVIDERS = {
    "tongyi": {
        "label": "通义千问",
        "model": "qwen-turbo",
        "base_url": "",
        "hint": "适合中文交互和日常雅思练习",
    },
    "deepseek": {
        "label": "DeepSeek",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "hint": "OpenAI兼容接口，性价比高",
    },
    "openai": {
        "label": "OpenAI",
        "model": "gpt-4o-mini",
        "base_url": "",
        "hint": "适合高质量反馈和长文本批改",
    },
    "custom": {
        "label": "OpenAI兼容接口",
        "model": "gpt-4o-mini",
        "base_url": "",
        "hint": "可接入自定义代理或兼容服务",
    },
}


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "ielts-dev-secret-key")


def build_task1_chart_assets(result_data, raw_text=""):
    return _build_task1_chart_assets(result_data, raw_text)


@app.template_filter("simple_md")
def simple_md_filter(text):
    return Markup(_simple_md_filter(text))


@app.template_filter("record_title")
def record_title_filter(activity):
    return learning_record_title(activity)


def _html_list(items):
    if not items:
        return ""
    if isinstance(items, str):
        return f"<p>{escape(items)}</p>"
    return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"


def _feedback_html(feedbacks):
    if not feedbacks:
        return ""
    blocks = []
    for index, feedback in enumerate(feedbacks, 1):
        data = feedback.get("result_data") if isinstance(feedback, dict) else None
        data = data if isinstance(data, dict) else {}
        body = []
        if feedback.get("timestamp"):
            body.append(f"<p class='record-meta'><strong>反馈时间：</strong>{escape(feedback['timestamp'])}</p>")
        if feedback.get("user_response"):
            body.append(f"<p><strong>当时我的回答：</strong></p><p>{escape(feedback['user_response'])}</p>")
        if data.get("overall_score") is not None:
            body.append(f"<p><strong>AI 评分：</strong>{escape(data['overall_score'])} / 9.0</p>")
        breakdown = data.get("breakdown")
        if isinstance(breakdown, dict):
            labels = {
                "fluency_coherence": "流利度与连贯性",
                "lexical_resource": "词汇资源",
                "grammatical_range_accuracy": "语法范围与准确性",
                "pronunciation": "发音",
            }
            for key, label in labels.items():
                item = breakdown.get(key)
                if not isinstance(item, dict):
                    continue
                detail = []
                if item.get("score") is not None:
                    detail.append(f"<p><strong>分数：</strong>{escape(item['score'])}</p>")
                for field, title in [
                    ("strengths", "优点"),
                    ("weaknesses", "待改进"),
                    ("suggestions", "建议"),
                    ("suggested_words", "推荐词汇"),
                    ("common_errors", "常见错误"),
                    ("improvement_tips", "改进提示"),
                ]:
                    if item.get(field):
                        detail.append(f"<p><strong>{title}：</strong></p>{_html_list(item[field])}")
                for field, title in [
                    ("vocabulary_analysis", "词汇分析"),
                    ("grammar_analysis", "语法分析"),
                    ("pronunciation_analysis", "发音分析"),
                ]:
                    if item.get(field):
                        detail.append(f"<p><strong>{title}：</strong>{escape(item[field])}</p>")
                if detail:
                    body.append(
                        f"<details class='result-accordion nested-answer'><summary>{label}</summary>"
                        f"<div class='result-body'>{''.join(detail)}</div></details>"
                    )
        if data.get("improved_response"):
            body.append(
                "<details class='result-accordion nested-answer'><summary>优化回答示例</summary>"
                f"<div class='result-body'><p>{escape(data['improved_response'])}</p></div></details>"
            )
        if data.get("practice_recommendations"):
            body.append(
                "<details class='result-accordion nested-answer'><summary>练习建议</summary>"
                f"<div class='result-body'>{_html_list(data['practice_recommendations'])}</div></details>"
            )
        if not data and feedback.get("result"):
            body.append(simple_md_filter(feedback["result"]))
        blocks.append(
            f"<details class='result-accordion nested-answer' open><summary>当时回答与 AI 评分 {index}</summary>"
            f"<div class='result-body'>{''.join(body)}</div></details>"
        )
    return "".join(blocks)


@app.template_filter("record_result")
def record_result_filter(result_data, activity=""):
    if not isinstance(result_data, dict):
        return Markup(f"<pre>{escape(str(result_data or ''))}</pre>")

    sections = []

    cue_card = result_data.get("cue_card")
    if cue_card:
        feedback_html = _feedback_html(result_data.get("_feedbacks"))
        sections.append(
            "<details class='result-accordion' open><summary>题目卡</summary>"
            f"<div class='result-body cue-card-body'>{simple_md_filter(cue_card)}{feedback_html}</div></details>"
        )

    if result_data.get("question"):
        task_type = result_data.get("task_type", "")
        title = "作文题目"
        if task_type == "Task 1":
            title = "小作文题目"
        elif task_type == "Task 2":
            title = "大作文题目"
        meta = []
        if result_data.get("chart_type"):
            meta.append(f"<p><strong>图表类型：</strong>{escape(result_data['chart_type'])}</p>")
        if result_data.get("chart_image"):
            meta.append(f"<div style='margin-top:12px'><img src='/{escape(result_data['chart_image'])}' alt='Task 1 chart' style='max-width:100%;border:1px solid var(--line);border-radius:12px;background:white'></div>")
        if result_data.get("table_data"):
            td = result_data["table_data"]
            headers_html = "".join(f"<th>{escape(str(h))}</th>" for h in td.get("headers", []))
            rows_html = ""
            for row in td.get("rows", []):
                cells = "".join(f"<td>{escape(str(c))}</td>" for c in row)
                rows_html += f"<tr>{cells}</tr>"
            meta.append(f"<div style='margin-top:12px;overflow-x:auto'><table class='data-table' style='width:100%'><thead><tr>{headers_html}</tr></thead><tbody>{rows_html}</tbody></table></div>")
        if result_data.get("topic_category"):
            meta.append(f"<p><strong>话题类别：</strong>{escape(result_data['topic_category'])}</p>")
        if result_data.get("essay_type"):
            meta.append(f"<p><strong>作文类型：</strong>{escape(result_data['essay_type'])}</p>")
        meta.append(
            "<p class='record-question'><strong>题目：</strong>"
            f"{escape(result_data['question'])}</p>"
        )
        if result_data.get("key_features"):
            meta.append(
                "<details class='result-accordion'><summary>📊 关键特征</summary>"
                f"<div class='result-body'>{_html_list(result_data['key_features'])}</div></details>"
            )
        if result_data.get("chart_data"):
            rows = "".join(
                f"<tr><td>{escape(row.get('label', ''))}</td><td>{escape(row.get('value', ''))}</td></tr>"
                for row in result_data["chart_data"]
                if isinstance(row, dict)
            )
            meta.append(
                "<details class='result-accordion'><summary>📋 表格数据（供 AI 互动使用）</summary>"
                f"<div class='result-body'><table class='data-table'><thead><tr><th>项目</th><th>数值</th></tr></thead><tbody>{rows}</tbody></table></div></details>"
            )
        if result_data.get("key_points"):
            meta.append(
                "<details class='result-accordion'><summary>💡 关键论点</summary>"
                f"<div class='result-body'>{_html_list(result_data['key_points'])}</div></details>"
            )
        if result_data.get("suggested_structure"):
            meta.append(
                "<details class='result-accordion'><summary>📐 建议结构</summary>"
                f"<div class='result-body'><p>{escape(result_data['suggested_structure'])}</p></div></details>"
            )

        sections.append(
            f"<details class='result-accordion' open><summary>{title}</summary>"
            f"<div class='result-body'>{''.join(meta)}</div></details>"
        )

    questions = result_data.get("questions")
    if isinstance(questions, list):
        for index, item in enumerate(questions, 1):
            if not isinstance(item, dict):
                continue
            body = [f"<p><strong>题目：</strong>{escape(item.get('question', ''))}</p>"]
            body.append(f"<button class='speak-btn' type='button' data-speak='{escape(item.get('question', ''))}'>朗读题目</button>")
            if item.get("keywords"):
                body.append(
                    "<details class='result-accordion nested-answer'><summary>🔑 关键词提示</summary>"
                    f"<div class='result-body'>{_html_list(item['keywords'])}</div></details>"
                )
            if item.get("tips"):
                body.append(
                    "<details class='result-accordion nested-answer'><summary>💡 回答技巧</summary>"
                    f"<div class='result-body'>{_html_list(item['tips'])}</div></details>"
                )
            if item.get("model_answer"):
                body.append(
                    "<details class='result-accordion nested-answer'><summary>📖 参考答案</summary>"
                    f"<div class='result-body'><button class='speak-btn' type='button' data-speak='{escape(item['model_answer'])}'>朗读参考答案</button><p>{escape(item['model_answer'])}</p></div></details>"
                )
            body.append(_feedback_html(item.get("_feedbacks")))
            sections.append(
                f"<details class='result-accordion' open><summary>Part 1 题目 {index}</summary>"
                f"<div class='result-body'>{''.join(body)}</div></details>"
            )


    discussion_questions = result_data.get("discussion_questions")
    if isinstance(discussion_questions, list):
        for index, item in enumerate(discussion_questions, 1):
            if not isinstance(item, dict):
                continue
            body = [f"<p><strong>题目：</strong>{escape(item.get('question', ''))}</p>"]
            body.append(f"<button class='speak-btn' type='button' data-speak='{escape(item.get('question', ''))}'>朗读题目</button>")
            if item.get("purpose"):
                body.append(f"<p><strong>考察点：</strong>{escape(item['purpose'])}</p>")
            if item.get("depth_required"):
                body.append(f"<p><strong>回答深度：</strong>{escape(item['depth_required'])}</p>")
            if item.get("model_response"):
                body.append(
                    "<details class='result-accordion nested-answer'><summary>参考回答</summary>"
                    f"<div class='result-body'><button class='speak-btn' type='button' data-speak='{escape(item['model_response'])}'>朗读参考答案</button><p>{escape(item['model_response'])}</p></div></details>"
                )
            body.append(_feedback_html(item.get("_feedbacks")))
            sections.append(
                f"<details class='result-accordion' open><summary>Part 3 题目 {index}</summary>"
                f"<div class='result-body'>{''.join(body)}</div></details>"
            )

    model_answer = result_data.get("model_answer")
    if isinstance(model_answer, dict):
        body = []
        speak_parts = []
        labels = {
            "introduction": "开头",
            "main_points": "主要观点",
            "details": "细节展开",
            "conclusion": "结尾",
        }
        for key in ["introduction", "main_points", "details", "conclusion"]:
            value = model_answer.get(key)
            if value:
                body.append(
                    f"<details class='result-accordion nested-answer'><summary>{labels[key]}</summary>"
                    f"<div class='result-body'>{_html_list(value) if isinstance(value, list) else f'<p>{escape(value)}</p>'}</div></details>"
                )
                if isinstance(value, list):
                    speak_parts.extend(str(item) for item in value)
                else:
                    speak_parts.append(str(value))
        if body:
            speak_html = ""
            if speak_parts:
                speak_text = " ".join(speak_parts)
                speak_html = f"<button class='speak-btn' type='button' data-speak='{escape(speak_text)}'>朗读参考答案</button>"
            sections.append(
                "<details class='result-accordion'><summary>参考答案</summary>"
                f"<div class='result-body'>{speak_html}{''.join(body)}</div></details>"
            )

    elif isinstance(model_answer, str) and model_answer.strip():
        sections.append(
            "<details class='result-accordion'><summary>参考答案</summary>"
            f"<div class='result-body'><button class='speak-btn' type='button' data-speak='{escape(model_answer)}'>朗读参考答案</button><p>{escape(model_answer)}</p></div></details>"
        )

    list_labels = {
        "vocabulary_highlight": "高级词汇",
        "grammar_structures": "语法结构",
        "fluency_tips": "流利度建议",
        "analytical_angles": "分析角度",
        "critical_thinking_tips": "批判性思维建议",
        "extended_vocabulary": "扩展词汇",
        "advanced_vocabulary": "高级词汇",
        "useful_phrases": "可套用短语",
        "strengths": "优点",
        "improvements": "改进建议",
    }
    for key, label in list_labels.items():
        value = result_data.get(key)
        if value:
            sections.append(
                f"<details class='result-accordion'><summary>{label}</summary>"
                f"<div class='result-body'>{_html_list(value)}</div></details>"
            )

    scalar_labels = {
        "overall_score": "总分",
        "band_description": "分数段说明",
        "suggested_corrections": "修改建议",
        "corrected_essay": "修正后作文",
        "model_essay": "参考范文",
        "full_answer": "完整答案",
        "answer_structure": "答案结构",
        "improvement_tips": "改进建议",
        "formatted_text": "内容",
    }
    for key, label in scalar_labels.items():
        value = result_data.get(key)
        if value:
            if key == "formatted_text":
                value = str(value).replace("无法解析为JSON格式的响应:\n\n", "")
            content = simple_md_filter(value) if key in {"corrected_essay", "model_essay", "suggested_corrections", "formatted_text"} else escape(value)
            speak_html = ""
            if key == "full_answer":
                speak_html = f"<button class='speak-btn' type='button' data-speak='{escape(value)}'>朗读答案</button>"
            sections.append(
                f"<details class='result-accordion'><summary>{label}</summary>"
                f"<div class='result-body'>{speak_html}{content}</div></details>"
            )

    if not sections:
        sections.append(f"<pre>{escape(json.dumps(result_data, ensure_ascii=False, indent=2))}</pre>")

    return Markup("".join(sections))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth"))
        return view(*args, **kwargs)

    return wrapped


@app.route("/data/audio/<user>/<fname>")
@login_required
def serve_audio(user, fname):
    from flask import send_from_directory
    audio_dir = os.path.join(os.path.dirname(__file__), "data", "audio", user)
    return send_from_directory(audio_dir, fname)


@app.route("/data/charts/<fname>")
@login_required
def serve_chart(fname):
    chart_dir = os.path.join(os.path.dirname(__file__), "data", "charts")
    return send_from_directory(chart_dir, fname)


def default_profile(user_id):
    return {
        "user_id": user_id,
        "full_name": "",
        "email": "",
        "current_level": 5.0,
        "listening_level": 5.0,
        "speaking_level": 5.0,
        "reading_level": 5.0,
        "writing_level": 5.0,
        "target_score": 6.5,
        "learning_goal": "",
        "weak_areas": ["口语", "写作"],
        "study_time": 10,
        "exam_date": "",
    }


def float_field(name, default):
    try:
        return float(request.form.get(name, default))
    except (TypeError, ValueError):
        return default


def int_field(name, default):
    try:
        return int(request.form.get(name, default))
    except (TypeError, ValueError):
        return default


def score_options(start=1.0, end=9.0):
    values = []
    value = start
    while value <= end:
        values.append(round(value, 1))
        value += 0.5
    return values


def current_assistant():
    user_id = session["user_id"]
    config = load_user_ai_config(user_id)
    api_key = config.get("api_key", "")
    if not api_key:
        return None, config
    assistant = TongyiIELTSAssistant(
        api_key,
        provider=config.get("provider", "tongyi"),
        model=config.get("model", ""),
        base_url=config.get("base_url", ""),
    )
    return assistant, config


def provider_status_for(ai_config):
    api_keys = ai_config.get("api_keys", {})
    return {key: bool(api_keys.get(key)) for key in AI_PROVIDERS}


def is_admin_user(user_id=None):
    user_id = user_id or session.get("user_id", "")
    raw = os.getenv("ADMIN_USER_IDS", os.getenv("ADMIN_USER_ID", "admin"))
    admins = {item.strip() for item in raw.split(",") if item.strip()}
    if user_id in admins:
        return True
    try:
        return user_is_admin(user_id)
    except Exception:
        return False


def _normalized_question(text):
    return " ".join(str(text or "").split())


def is_speaking_feedback_record(record):
    data = record.get("data") if isinstance(record, dict) else {}
    return record.get("activity") == "口语反馈" or (isinstance(data, dict) and data.get("mode") == "speaking_feedback")


def attach_speaking_feedback(records):
    feedback_by_question = {}
    for record in records:
        if not is_speaking_feedback_record(record):
            continue
        data = record.get("data") or {}
        question_key = _normalized_question(data.get("question", ""))
        if not question_key:
            continue
        feedback_by_question.setdefault(question_key, []).append({
            "id": record.get("id"),
            "timestamp": record.get("timestamp", ""),
            "user_response": data.get("user_response", ""),
            "result": data.get("result", ""),
            "result_data": data.get("result_data"),
        })

    for record in records:
        if is_speaking_feedback_record(record):
            continue
        data = record.get("data") or {}
        result_data = data.get("result_data")
        if not isinstance(result_data, dict):
            continue
        if isinstance(result_data.get("questions"), list):
            for item in result_data["questions"]:
                if isinstance(item, dict):
                    feedbacks = feedback_by_question.get(_normalized_question(item.get("question", "")), [])
                    if feedbacks:
                        item["_feedbacks"] = feedbacks
        if isinstance(result_data.get("discussion_questions"), list):
            for item in result_data["discussion_questions"]:
                if isinstance(item, dict):
                    feedbacks = feedback_by_question.get(_normalized_question(item.get("question", "")), [])
                    if feedbacks:
                        item["_feedbacks"] = feedbacks
        if result_data.get("cue_card"):
            feedbacks = feedback_by_question.get(_normalized_question(result_data.get("cue_card", "")), [])
            if feedbacks:
                result_data["_feedbacks"] = feedbacks
    return records


def visible_progress(records):
    return [
        record for record in records
        if record.get("activity") != "学习计划" and not is_speaking_feedback_record(record)
    ]


def prepare_progress(records):
    return visible_progress(attach_speaking_feedback(records))


def prepare_feedback_context(records):
    return attach_speaking_feedback(records)



def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth"))
        if not is_admin_user():
            flash("需要管理员权限。", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped


def _normalize_base_url(value):
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    return f"http://{value}"


def _request_base_url():
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip()
    scheme = forwarded_proto or request.scheme or "http"
    host = request.headers.get("X-Forwarded-Host", "").split(",")[0].strip() or request.host
    return f"{scheme}://{host}".rstrip("/")


def _is_private_host(hostname):
    try:
        ip = ipaddress.ip_address((hostname or "").strip("[]"))
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


def _should_ignore_private_env_host(env_url):
    env_host = urlsplit(_normalize_base_url(env_url)).hostname or ""
    request_host = urlsplit(_request_base_url()).hostname or ""
    return _is_private_host(env_host) and request_host and not _is_private_host(request_host)


def _replace_url_port(base_url, port):
    parts = urlsplit(_normalize_base_url(base_url))
    hostname = parts.hostname or parts.netloc
    if not hostname:
        return ""
    netloc = hostname
    if ":" in hostname and not hostname.startswith("["):
        netloc = f"[{hostname}]"
    if parts.username:
        userinfo = parts.username
        if parts.password:
            userinfo += f":{parts.password}"
        netloc = f"{userinfo}@{netloc}"
    if port:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parts.scheme or "http", netloc, "", "", "")).rstrip("/")


def _legacy_streamlit_base_url():
    explicit = _normalize_base_url(os.getenv("LEGACY_STREAMLIT_URL", ""))
    if explicit and not _should_ignore_private_env_host(explicit):
        return explicit
    domain = _normalize_base_url(os.getenv("SERVER_DOMAIN", ""))
    streamlit_port = os.getenv("STREAMLIT_PORT", "8501")
    if domain and not _should_ignore_private_env_host(domain):
        return _replace_url_port(domain, streamlit_port)
    return _replace_url_port(_request_base_url(), streamlit_port)





def common_context():
    user_id = session["user_id"]
    profile = load_user_profile(user_id) or default_profile(user_id)
    ai_config = load_user_ai_config(user_id)
    x_token = _cross_login_token(user_id)
    _legacy_url = _legacy_streamlit_base_url()
    return {
        "user_id": user_id,
        "profile": profile,
        "ai_config": ai_config,
        "providers": AI_PROVIDERS,
        "provider_status": provider_status_for(ai_config),
        "is_admin": is_admin_user(user_id),
        "legacy_streamlit_url": _legacy_url,
        "streamlit_cross_url": f"{_legacy_url}?user_id={user_id}&x_token={x_token}",
    }


def lookup_word_locally(word: str) -> dict:
    normalized = word.strip().lower()
    for item in IELTS_WORDS:
        if item["word"].lower() == normalized:
            return {
                "word": item["word"],
                "translation": item["meaning"],
                "phrases": item["phrases"],
                "usage": item["essay_use"],
                "source": "雅思词库",
            }
    return {
        "word": word,
        "translation": "暂未在内置词库中找到，可保存到生词本后继续复习。",
        "phrases": [],
        "usage": "建议结合上下文判断词性和含义，再用 AI 查询更完整的作文用法。",
        "source": "临时查询",
    }


def parse_model_output(raw):
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return {"formatted_text": raw, "raw_response": raw}



@app.before_request
def ensure_database():
    initialize_database()
    # 跨版本自动登录：来自 Streamlit 的 x_token 在任意页面都生效
    if "user_id" not in session:
        x_user = request.args.get("user_id", "").strip()
        x_token = request.args.get("x_token", "")
        if x_user and x_token and _verify_cross_token(x_user, x_token):
            profile = load_user_profile(x_user)
            if profile:
                session["user_id"] = x_user


@app.route("/", methods=["GET", "POST"])
def auth():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    # 跨版本自动登录：来自 Streamlit 的 x_token 校验
    x_user = request.args.get("user_id", "").strip()
    x_token = request.args.get("x_token", "")
    if x_user and x_token and _verify_cross_token(x_user, x_token):
        profile = load_user_profile(x_user)
        if profile:
            session["user_id"] = x_user
            flash("已从旧版自动登录。", "success")
            return redirect(url_for("dashboard"))
        flash("跨版本自动登录失败，用户不存在。", "error")
        return redirect(url_for("auth"))

    mode = request.form.get("mode", "login")
    if request.method == "POST":
        user_id = request.form.get("user_id", "").strip()
        password = request.form.get("password", "")

        if not user_id or not password:
            flash("请输入用户ID和密码。", "error")
            return redirect(url_for("auth", mode=mode))

        if mode == "register":
            confirm_password = request.form.get("confirm_password", "")
            if len(password) < 4:
                flash("密码至少需要4位。", "error")
                return redirect(url_for("auth", mode="register"))
            if password != confirm_password:
                flash("两次输入的密码不一致。", "error")
                return redirect(url_for("auth", mode="register"))
            if not register_user(user_id, password):
                flash("该用户ID已存在，请直接登录。", "error")
                return redirect(url_for("auth", mode="register"))

            session["user_id"] = user_id
            flash("注册成功，已自动登录。", "success")
            return redirect(url_for("dashboard"))

        if authenticate_user(user_id, password):
            session["user_id"] = user_id
            flash("欢迎回来。", "success")
            return redirect(url_for("dashboard"))

        flash("用户不存在或密码不正确。", "error")
        return redirect(url_for("auth"))

    return render_template("auth.html", mode=request.args.get("mode", "login"), streamlit_url=_legacy_streamlit_base_url())


@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]
    date_filter = request.args.get("date", "").strip()
    progress = prepare_progress(list(reversed(get_progress(user_id, limit=160))))
    if date_filter:
        progress = [p for p in progress if (p.get("timestamp") or "").startswith(date_filter)]
    progress = progress[:12]
    suggestions = session.pop("improvement_suggestions", None)
    return render_template(
        "dashboard.html",
        progress=progress,
        suggestions=suggestions,
        date_filter=date_filter,
        score_options=score_options(),
        target_options=score_options(4.0, 9.0),
        **common_context(),
    )


@app.post("/generate-suggestions")
@login_required
def generate_suggestions():
    user_id = session["user_id"]
    profile = load_user_profile(user_id) or default_profile(user_id)
    progress = prepare_progress(list(reversed(get_progress(user_id, limit=100))))
    assistant, _ = current_assistant()
    if assistant is None:
        flash("请先保存可用的 AI API Key。", "error")
        return redirect(url_for("dashboard"))
    weak_areas = profile.get("weak_areas", [])
    if isinstance(weak_areas, str):
        try:
            weak_areas = json.loads(weak_areas)
        except (TypeError, ValueError):
            weak_areas = [weak_areas] if weak_areas else []
    target_score = profile.get("target_score", 6.5)
    current_level = profile.get("current_level", 5.0)
    suggestions = assistant.generate_improvement_suggestions(
        progress, weak_areas, float(target_score), float(current_level)
    )
    session["improvement_suggestions"] = suggestions
    flash("重点提升建议已生成。", "success")
    return redirect(url_for("dashboard"))


@app.post("/profile")
@login_required
def update_profile():
    user_id = session["user_id"]
    profile = {
        "user_id": user_id,
        "full_name": request.form.get("full_name", "").strip(),
        "email": request.form.get("email", "").strip(),
        "listening_level": float_field("listening_level", 5.0),
        "speaking_level": float_field("speaking_level", 5.0),
        "reading_level": float_field("reading_level", 5.0),
        "writing_level": float_field("writing_level", 5.0),
        "target_score": float_field("target_score", 6.5),
        "learning_goal": request.form.get("learning_goal", "").strip(),
        "weak_areas": request.form.getlist("weak_areas"),
        "study_time": int_field("study_time", 10),
        "exam_date": request.form.get("exam_date", ""),
    }
    save_user_profile(user_id, profile)
    flash("用户资料和学习目标已保存。", "success")
    return redirect(url_for("settings_page"))


@app.post("/ai-config")
@login_required
def update_ai_config():
    user_id = session["user_id"]
    provider = request.form.get("provider", "tongyi")
    defaults = AI_PROVIDERS.get(provider, AI_PROVIDERS["tongyi"])
    api_key = request.form.get("api_key", "").strip()
    model = request.form.get("model", "").strip() or defaults["model"]
    base_url = request.form.get("base_url", "").strip() or defaults["base_url"]

    if not api_key:
        flash("请输入该模型供应商的 API Key。", "error")
        return redirect(url_for("settings_page"))

    save_user_ai_config(user_id, provider, api_key, model, base_url)
    flash("AI 模型配置已保存。", "success")
    return redirect(url_for("settings_page"))


@app.post("/ai-provider")
@login_required
def update_active_ai_provider():
    user_id = session["user_id"]
    provider = request.form.get("provider", "tongyi")
    ai_config = load_user_ai_config(user_id)
    api_keys = ai_config.get("api_keys", {})
    if not api_keys.get(provider):
        flash("请先在用户中心保存该模型的 API Key。", "error")
        return redirect(request.referrer or url_for("dashboard"))

    defaults = AI_PROVIDERS.get(provider, AI_PROVIDERS["tongyi"])
    save_user_ai_config(
        user_id,
        provider,
        api_keys[provider],
        request.form.get("model", "").strip() or defaults["model"],
        request.form.get("base_url", "").strip() or defaults["base_url"],
    )
    flash(f"已切换到 {defaults['label']}。", "success")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/admin")
@admin_required
def admin_panel():
    selected_user = request.args.get("user_id", "").strip()
    users = list_users()
    for item in users:
        item["is_admin"] = bool(item.get("is_admin")) or is_admin_user(item.get("user_id"))
    selected_profile = load_user_profile(selected_user) if selected_user else None
    selected_ai_config = load_user_ai_config(selected_user) if selected_user else None
    selected_is_admin = is_admin_user(selected_user) if selected_user else False
    records = prepare_progress(get_all_progress(limit=500, user_id=selected_user))
    return render_template(
        "admin.html",
        users=users,
        records=records,
        selected_user=selected_user,
        selected_profile=selected_profile,
        selected_ai_config=selected_ai_config,
        selected_is_admin=selected_is_admin,
        score_options=score_options(),
        target_options=score_options(4.0, 9.0),
        **common_context(),
    )


@app.post("/admin/users/<target_user>/profile")
@admin_required
def admin_update_user_profile(target_user):
    profile = {
        "user_id": target_user,
        "full_name": request.form.get("full_name", "").strip(),
        "email": request.form.get("email", "").strip(),
        "listening_level": float_field("listening_level", 5.0),
        "speaking_level": float_field("speaking_level", 5.0),
        "reading_level": float_field("reading_level", 5.0),
        "writing_level": float_field("writing_level", 5.0),
        "target_score": float_field("target_score", 6.5),
        "learning_goal": request.form.get("learning_goal", "").strip(),
        "weak_areas": request.form.getlist("weak_areas"),
        "study_time": int_field("study_time", 10),
        "exam_date": request.form.get("exam_date", ""),
    }
    save_user_profile(target_user, profile)
    set_user_admin(target_user, request.form.get("is_admin") == "1")
    flash(f"用户 {target_user} 的资料已保存。", "success")
    return redirect(url_for("admin_panel", user_id=target_user))


@app.post("/admin/users/<target_user>/password")
@admin_required
def admin_update_user_password(target_user):
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")
    if len(password) < 4:
        flash("新密码至少需要4位。", "error")
    elif password != confirm:
        flash("两次输入的密码不一致。", "error")
    elif update_user_password(target_user, password):
        flash(f"用户 {target_user} 的密码已更新。", "success")
    else:
        flash("用户不存在或密码更新失败。", "error")
    return redirect(url_for("admin_panel", user_id=target_user))


@app.post("/admin/users/<target_user>/ai-config")
@admin_required
def admin_update_user_ai_config(target_user):
    provider = request.form.get("provider", "tongyi")
    defaults = AI_PROVIDERS.get(provider, AI_PROVIDERS["tongyi"])
    api_keys = {
        key: request.form.get(f"api_key_{key}", "").strip()
        for key in AI_PROVIDERS
    }
    model = request.form.get("model", "").strip() or defaults["model"]
    base_url = request.form.get("base_url", "").strip() or defaults["base_url"]
    save_user_ai_config_map(target_user, provider, api_keys, model, base_url)
    flash(f"用户 {target_user} 的 AI 配置已保存。", "success")
    return redirect(url_for("admin_panel", user_id=target_user))


@app.post("/admin/users/<target_user>/role")
@admin_required
def admin_update_user_role(target_user):
    set_user_admin(target_user, request.form.get("is_admin") == "1")
    flash(f"用户 {target_user} 的管理员权限已更新。", "success")
    return redirect(url_for("admin_panel", user_id=target_user))


@app.post("/admin/users/<target_user>/delete")
@admin_required
def admin_delete_user(target_user):
    if target_user == session.get("user_id"):
        flash("不能删除当前登录的管理员账号。", "error")
    elif delete_user(target_user):
        flash(f"用户 {target_user} 已删除。", "success")
    else:
        flash("用户不存在或删除失败。", "error")
    return redirect(url_for("admin_panel"))


@app.post("/records/<int:record_id>/delete")
@login_required
def delete_record(record_id):
    next_url = request.form.get("next") or url_for("dashboard", _anchor="history")
    if is_admin_user() and request.form.get("scope") == "admin":
        ok = delete_progress_record_by_id(record_id)
    else:
        ok = delete_progress_record_by_id(record_id, session["user_id"])
    flash("练习记录已删除。" if ok else "记录不存在或无权删除。", "success" if ok else "error")
    return redirect(next_url)


@app.route("/settings")
@login_required
def settings_page():
    return render_template("settings.html", score_options=score_options(), target_options=score_options(4.0, 9.0), **common_context())


@app.route("/assistant", methods=["GET", "POST"])
@login_required
def assistant_center():
    result = None
    mode = request.form.get("mode", "writing_ideas")
    assistant, ai_config = current_assistant()
    if request.method == "POST":
        if assistant is None:
            flash("请先在用户中心保存可用的 AI API Key。", "error")
            return redirect(url_for("dashboard"))

        if mode == "writing_ideas":
            topic = request.form.get("topic", "").strip()
            question = request.form.get("question", "").strip()
            result = assistant.generate_writing_ideas(topic, question)
            save_progress(session["user_id"], "作文思路互动", {"topic": topic, "question": question})

        elif mode == "speaking_part2":
            topic = request.form.get("speaking_topic", "人物描述")
            cue_type = request.form.get("cue_type", "描述类")
            result = assistant.practice_speaking_part2(topic, cue_type)
            save_progress(session["user_id"], "口语Part 2题目生成", {"topic": topic, "cue_type": cue_type})

    return render_template(
        "assistant.html",
        result=result,
        mode=mode,
        **common_context(),
    )


@app.route("/speaking", methods=["GET", "POST"])
@login_required
def speaking():
    result = None
    result_data = None
    mode = request.form.get("mode") or request.args.get("mode", "part1")
    assistant, ai_config = current_assistant()
    if request.method == "POST":
        if assistant is None:
            flash("请先在用户中心保存可用的 AI API Key。", "error")
            return redirect(url_for("dashboard"))
        if mode == "part1":
            topic = request.form.get("topic", "工作/学习")
            difficulty = request.form.get("difficulty", "中等")
            result = assistant.practice_speaking_part1(
                topic,
                difficulty,
            )
            result_data = parse_model_output(result)
            save_progress(session["user_id"], "口语Part 1题目生成", {
                "mode": mode,
                "topic": topic,
                "difficulty": difficulty,
                "result": result,
                "result_data": result_data,
            })
        elif mode == "part2":
            topic = request.form.get("topic", "人物描述")
            cue_type = request.form.get("cue_type", "描述类")
            result = assistant.practice_speaking_part2(
                topic,
                cue_type,
            )
            result_data = parse_model_output(result)
            save_progress(session["user_id"], "口语Part 2题目生成", {
                "mode": mode,
                "topic": topic,
                "cue_type": cue_type,
                "result": result,
                "result_data": result_data,
            })
        elif mode == "part3":
            part2_topic = request.form.get("part2_topic", "")
            discussion_type = request.form.get("discussion_type", "社会影响")
            result = assistant.practice_speaking_part3(
                part2_topic,
                discussion_type,
            )
            result_data = parse_model_output(result)
            save_progress(session["user_id"], "口语Part 3题目生成", {
                "mode": mode,
                "topic": part2_topic,
                "discussion_type": discussion_type,
                "result": result,
                "result_data": result_data,
            })
        elif mode == "speaking_feedback":
            question = request.form.get("question", "").strip()
            user_response = request.form.get("user_response", "").strip()
            target_score = float_field("target_score", 6.5)
            result = assistant.get_speaking_feedback_direct(
                question,
                user_response,
                target_score,
            )
            result_data = parse_model_output(result)
            save_progress(session["user_id"], "口语反馈", {
                "mode": mode,
                "question": question,
                "user_response": user_response,
                "result": result,
                "result_data": result_data,
            })
        elif mode == "keyword_answer":
            question = request.form.get("question", "").strip()
            keywords = request.form.get("keywords", "").strip()
            part = request.form.get("part", "Part 2")
            result = assistant.generate_answer_from_keywords(
                question,
                keywords,
                part,
            )
            result_data = parse_model_output(result)
            save_progress(session["user_id"], "关键词生成答案", {
                "mode": mode,
                "question": question,
                "keywords": keywords,
                "result": result,
                "result_data": result_data,
            })
        elif mode == "answer_from_cn":
            question = request.form.get("question", "").strip()
            chinese_answer = request.form.get("chinese_answer", "").strip()
            result = assistant.generate_answer_from_cn(question, chinese_answer)
            save_progress(session["user_id"], "中文思路生成英文口语答案", {
                "mode": mode,
                "question": question,
                "chinese_answer": chinese_answer,
                "result": result,
            })
        if result is not None:
            session["speaking_result"] = result
            session["speaking_result_data"] = json.dumps(result_data) if result_data is not None else None
            session["speaking_mode"] = mode
    else:
        cached = session.pop("speaking_result", None)
        cached_data = session.pop("speaking_result_data", None)
        cached_mode = session.pop("speaking_mode", "part1")
        if cached is not None:
            result = cached
            mode = cached_mode
            if cached_data is not None:
                try:
                    result_data = json.loads(cached_data)
                except (TypeError, ValueError):
                    result_data = None
    return render_template("speaking.html", result=result, result_data=result_data, mode=mode, **common_context())


@app.route("/theme-linking", methods=["GET", "POST"])
@login_required
def theme_linking():
    result = None
    result_data = None
    assistant, ai_config = current_assistant()
    if request.method == "POST":
        if assistant is None:
            flash("请先在用户中心保存可用的 AI API Key。", "error")
            return redirect(url_for("dashboard"))
        topics = [item.strip() for item in request.form.get("topics", "").splitlines() if item.strip()]
        result = assistant.link_speaking_themes(
            topics,
            request.form.get("main_theme", "个人成长"),
            float_field("target_score", 6.5),
        )
        result_data = parse_model_output(result)
        save_progress(session["user_id"], "口语串题方案", {"topics": topics, "result": result, "result_data": result_data})
        if result is not None:
            session["theme_linking_result"] = result
            session["theme_linking_result_data"] = result_data
    else:
        cached = session.pop("theme_linking_result", None)
        if cached is not None:
            result = cached
            result_data = session.pop("theme_linking_result_data", None)
    return render_template("theme_linking.html", result=result, result_data=result_data, **common_context())


@app.route("/writing", methods=["GET", "POST"])
@login_required
def writing():
    result = None
    result_data = None
    mode = request.form.get("mode", "task1")
    assistant, ai_config = current_assistant()
    if request.method == "POST":
        if assistant is None:
            flash("请先在用户中心保存可用的 AI API Key。", "error")
            return redirect(url_for("dashboard"))
        if mode == "generate_topic":
            task_type = request.form.get("task_type", "Task 2")
            chart_type = request.form.get("chart_type", "柱状图")
            topic = request.form.get("topic", "教育")
            result = assistant.generate_writing_topic(task_type, chart_type=chart_type, topic=topic)
            result_data = parse_generated_topic_md(result, task_type)
            result_data = build_task1_chart_assets(result_data, raw_text=result)
            session["generated_topic_text"] = result_data.get("question", "")
            session["generated_topic_task"] = task_type
            save_progress(session["user_id"], "生成作文题目", {
                "mode": mode,
                "task_type": task_type,
                "result": result,
                "result_data": result_data,
            })
        elif mode == "ideas":
            topic = request.form.get("topic", "").strip()
            question = request.form.get("question", "").strip()
            chart_data = request.form.get("chart_data", "").strip()
            result = assistant.generate_writing_ideas_with_chart(topic, chart_data, question)
            result_data = parse_model_output(result)
            session["writing_ideas_topic"] = topic
            session["writing_ideas_question"] = question
            save_progress(session["user_id"], "作文思路互动", {
                "mode": mode,
                "topic": topic,
                "chart_data": chart_data,
                "question": question,
                "result": result,
                "result_data": result_data,
            })
        elif mode == "task1":
            task_type = request.form.get("task_type", "图表描述")
            essay_content = request.form.get("essay_content", "")
            target_score = float_field("target_score", 6.5)
            result = assistant.correct_writing_task1(
                task_type,
                essay_content,
                target_score,
            )
            result_data = parse_model_output(result)
            save_progress(session["user_id"], "写作 Task 1 批改", {
                "mode": mode,
                "task_type": task_type,
                "essay_content": essay_content,
                "target_score": target_score,
                "score": result_data.get("overall_score") if isinstance(result_data, dict) else None,
                "result": result,
                "result_data": result_data,
            })
        elif mode == "task2":
            topic_category = request.form.get("topic_category", "教育")
            essay_type = request.form.get("essay_type", "议论文")
            essay_content = request.form.get("essay_content", "")
            target_score = float_field("target_score", 6.5)
            result = assistant.correct_writing_task2(
                topic_category,
                essay_type,
                essay_content,
                target_score,
            )
            result_data = parse_model_output(result)
            save_progress(session["user_id"], "写作 Task 2 批改", {
                "mode": mode,
                "topic_category": topic_category,
                "essay_type": essay_type,
                "essay_content": essay_content,
                "target_score": target_score,
                "score": result_data.get("overall_score") if isinstance(result_data, dict) else None,
                "result": result,
                "result_data": result_data,
            })
        elif mode == "generate_model_answer":
            topic = request.form.get("topic", "").strip()
            task_type = request.form.get("task_type", "Task 2")
            result = assistant.generate_model_answer(task_type, topic)
            result_data = None
            save_progress(session["user_id"], "生成参考范文", {
                "mode": mode,
                "topic": topic,
                "task_type": task_type,
                "result": result,
            })
        if result is not None:
            session["writing_result"] = result
            session["writing_result_data"] = json.dumps(result_data) if result_data is not None else None
            session["writing_mode"] = mode
    else:
        cached = session.pop("writing_result", None)
        cached_data = session.pop("writing_result_data", None)
        cached_mode = session.pop("writing_mode", "task1")
        if cached is not None:
            result = cached
            mode = cached_mode
            if cached_data is not None:
                try:
                    result_data = json.loads(cached_data)
                except (TypeError, ValueError):
                    result_data = None

    # 处理题目导入：从生成题目区域导入到练习区
    import_topic = request.args.get("import_topic", "").strip()
    import_question = request.args.get("import_question", "").strip()
    import_task = request.args.get("import_task", "Task 2").strip()

    # 处理写作思路互动的题目显示
    ideas_topic = session.pop("writing_ideas_topic", None)
    ideas_question = session.pop("writing_ideas_question", None)

    # 生成的作文题目自动填充（无需手动导入）
    gen_topic_text = session.pop("generated_topic_text", None)
    gen_topic_task = session.pop("generated_topic_task", None)

    return render_template("writing.html",
        result=result, result_data=result_data, mode=mode,
        import_question=import_question,
        import_task=import_task,
        import_topic=import_topic,
        ideas_topic=ideas_topic,
        ideas_question=ideas_question,
        generated_topic_text=gen_topic_text,
        generated_topic_task=gen_topic_task,
        **common_context())


@app.route("/analysis")
@login_required
def analysis():
    user_id = session["user_id"]
    progress = prepare_progress(list(reversed(get_progress(user_id, limit=160))))
    user_words = get_user_words(user_id)
    return render_template(
        "analysis.html",
        progress=progress,
        user_words=user_words,
        **common_context(),
    )


@app.route("/vocabulary")
@login_required
def vocabulary():
    query = request.args.get("q", "").strip().lower()
    topic = request.args.get("topic", "")
    progress = get_vocab_progress(session["user_id"])
    user_words = get_user_words(session["user_id"])
    words = IELTS_WORDS
    if query:
        words = [
            item for item in words
            if query in item["word"].lower() or query in item["meaning"].lower()
        ]
    if topic:
        words = [item for item in words if item["topic"] == topic]
    topics = sorted({item["topic"] for item in IELTS_WORDS})
    learned_count = sum(1 for item in IELTS_WORDS if progress.get(item["word"], {}).get("status") == "learned")
    return render_template(
        "vocabulary.html",
        words=words,
        topics=topics,
        progress=progress,
        learned_count=learned_count,
        total_count=len(IELTS_WORDS),
        user_words=user_words,
        selected_topic=topic,
        query=query,
        **common_context(),
    )


@app.post("/vocabulary/<word>/progress")
@login_required
def vocabulary_progress(word):
    status = request.form.get("status", "learned")
    save_vocab_progress(session["user_id"], word, status)
    flash(f"{word} 已标记为{ '已掌握' if status == 'learned' else '学习中' }。", "success")
    return redirect(url_for("vocabulary"))


@app.post("/api/word-lookup")
@login_required
def word_lookup():
    data = request.get_json(silent=True) or {}
    word = (data.get("word") or "").strip().strip(".,;:!?()[]{}\"'")
    if not word:
        return jsonify({"error": "empty word"}), 400

    local = lookup_word_locally(word)
    assistant, _ = current_assistant()
    if assistant is not None:
        try:
            raw = assistant.explain_word(word)
            parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
            local.update({
                "translation": parsed.get("translation", local["translation"]),
                "phrases": parsed.get("phrases", local["phrases"]),
                "usage": parsed.get("usage", local["usage"]),
                "source": "AI 查询",
            })
        except Exception:
            pass
    return jsonify(local)


@app.post("/api/wordbook")
@login_required
def add_wordbook():
    data = request.get_json(silent=True) or {}
    word = (data.get("word") or "").strip()
    if not word:
        return jsonify({"error": "empty word"}), 400
    save_user_word(
        session["user_id"],
        word,
        data.get("translation", ""),
        data.get("usage", ""),
        data.get("source", "训练收藏"),
    )
    return jsonify({"ok": True})


@app.post("/api/speech-score")
@login_required
def api_speech_score():
    import uuid, tempfile
    user_id = session["user_id"]
    audio_file = request.files.get("audio")
    user_text = request.form.get("user_response", "").strip()
    question = request.form.get("question", "口语练习").strip()
    target_score = float(request.form.get("target_score", "6.5"))
    save_recording = request.form.get("save_recording", "1") == "1"

    saved_filename = None

    if audio_file:
        suffix = ".webm"
        if audio_file.filename and audio_file.filename.endswith(".m4a"):
            suffix = ".m4a"
        fname = f"{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{suffix}"
        user_dir = os.path.join(os.path.dirname(__file__), "data", "audio", user_id)
        os.makedirs(user_dir, exist_ok=True)
        saved_path = os.path.join(user_dir, fname)
        audio_file.save(saved_path)
        saved_filename = f"data/audio/{user_id}/{fname}"

    if not audio_file and not user_text:
        return jsonify({"error": "没有录音数据或文字内容"}), 400

    transcript = user_text
    score_result = ""
    feedback_text = ""

    # 尝试评分
    assistant, _ = current_assistant()
    if assistant and (user_text or saved_filename):
        try:
            if not user_text and saved_filename:
                from agents import TongyiIELTSAssistant
                if hasattr(assistant, 'llm'):
                    import base64
                    with open(saved_path, "rb") as f:
                        audio_b64 = base64.b64encode(f.read()).decode()
                    transcript = assistant.transcribe_audio()

            if transcript and len(transcript) > 10:
                feedback = assistant.get_speaking_feedback_direct(
                    question=question,
                    user_response=transcript,
                    target_score=target_score
                )
                feedback_text = feedback
        except Exception as e:
            feedback_text = f"评分出错：{e}"

    # 保存训练记录
    if save_recording and transcript and len(transcript) > 5:
        save_progress(user_id, "口语录音练习", {
            "question": question,
            "transcript": transcript,
            "score": score_result,
            "feedback": feedback_text,
            "audio_file": saved_filename or "",
            "mode": "speaking_recording",
        })

    response_data = {"transcript": transcript}
    if score_result:
        response_data["score_box"] = f"<strong>评分结果</strong><br>综合得分：{score_result}<br><small>{feedback_text}</small>"
    if saved_filename:
        response_data["audio_saved"] = saved_filename

    return jsonify(response_data)


@app.get("/api/recordings")
@login_required
def api_list_recordings():
    user_id = session["user_id"]
    progress = get_progress(user_id, limit=100)
    recordings = []
    for item in progress:
        data = item.get("data") or {}
        if data.get("audio_file") or data.get("mode") == "speaking_recording":
            recordings.append({
                "activity": item.get("activity", ""),
                "timestamp": item.get("timestamp", ""),
                "question": data.get("question", ""),
                "transcript": data.get("transcript", ""),
                "score": data.get("score", ""),
                "feedback": data.get("feedback", ""),
                "audio_file": data.get("audio_file", ""),
            })
    return jsonify({"recordings": recordings})


@app.post("/api/recordings/delete")
@login_required
def api_delete_recording():
    data = request.get_json(silent=True) or {}
    audio_file = (data.get("audio_file") or "").strip()
    timestamp = (data.get("timestamp") or "").strip()

    if not audio_file and not timestamp:
        return jsonify({"error": "need audio_file or timestamp"}), 400

    user_id = session["user_id"]
    progress = get_progress(user_id, limit=200)

    for item in progress:
        d = item.get("data") or {}
        match = False
        if audio_file and d.get("audio_file") == audio_file:
            match = True
        if timestamp and item.get("timestamp") == timestamp:
            match = True
        if match:
            path = os.path.join(os.path.dirname(__file__), d.get("audio_file", ""))
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except Exception:
                pass
            delete_progress_record(user_id, item.get("timestamp", ""))
            return jsonify({"ok": True})

    return jsonify({"error": "recording not found"}), 404


@app.get("/replay")
@login_required
def replay():
    ts = request.args.get("ts", "").strip()
    record_id = request.args.get("id", "").strip()
    if not ts and not record_id:
        flash("缺少记录标识。", "warning")
        return redirect(url_for("dashboard"))
    records = get_progress(session["user_id"], limit=500)
    for item in records:
        if (record_id and str(item.get("id")) == record_id) or (ts and item.get("timestamp") == ts):
            data = item.get("data") or {}
            mode = data.get("mode", "")
            if mode in ("part1", "part2", "part3"):
                if data.get("result") or data.get("result_data"):
                    session["speaking_result"] = data.get("result") or json.dumps(data.get("result_data"), ensure_ascii=False)
                    session["speaking_result_data"] = json.dumps(data.get("result_data")) if data.get("result_data") is not None else None
                    session["speaking_mode"] = mode
                return redirect(url_for("speaking", mode=mode))
            if mode in ("task1", "task2", "generate_topic"):
                if mode == "generate_topic" and (data.get("result") or data.get("result_data")):
                    session["writing_result"] = data.get("result") or json.dumps(data.get("result_data"), ensure_ascii=False)
                    session["writing_result_data"] = json.dumps(data.get("result_data")) if data.get("result_data") is not None else None
                    session["writing_mode"] = mode
                    return redirect(url_for("writing"))
                task_type_data = data.get("task_type", data.get("chart_type", "Task 2"))
                if "Task 1" in str(task_type_data):
                    task_mode = "task1"
                else:
                    task_mode = "task2"
                question = data.get("question", "")
                if not question and isinstance(data.get("result_data"), dict):
                    question = data["result_data"].get("question", "")
                if not question:
                    question = data.get("essay_content", "")
                return redirect(url_for("writing", **{
                    "import_topic": "1",
                    "import_question": question,
                    "import_task": "Task 1" if task_mode == "task1" else "Task 2",
                }))
            if mode == "ideas":
                if data.get("result") or data.get("result_data"):
                    session["writing_result"] = data.get("result") or json.dumps(data.get("result_data"), ensure_ascii=False)
                    session["writing_result_data"] = json.dumps(data.get("result_data")) if data.get("result_data") is not None else None
                    session["writing_mode"] = mode
                return redirect(url_for("writing", **{
                    "import_topic": "1",
                    "import_question": data.get("topic", ""),
                    "import_task": "Task 2",
                }))
            if mode in ("theme_linking",):
                return redirect(url_for("theme_linking", **{
                    "preset_topics": data.get("topics", ""),
                }))
            return redirect(url_for("dashboard"))
    flash("记录未找到。", "warning")
    return redirect(url_for("dashboard"))


@app.post("/logout")
def logout():
    session.clear()
    flash("已退出登录。", "success")
    return redirect(url_for("auth"))


if __name__ == "__main__":
    port = int(os.getenv("WEB_PORT", "8600"))
    print(f" * 信达雅启动于 http://0.0.0.0:{port}")
    from waitress import serve
    serve(app, host="0.0.0.0", port=port)
