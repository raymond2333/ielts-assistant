import json
import re
import hmac
import hashlib
import random
import uuid
import pandas as pd
from typing import Dict, Any, List, Tuple
import streamlit as st
from datetime import datetime, timedelta
import os

from database import (
    authenticate_user as _authenticate_user,
    get_database_status as _get_database_status,
    get_progress,
    initialize_database as _initialize_database,
    is_mysql_configured,
    load_user_ai_config as _load_user_ai_config,
    load_user_api_key as _load_user_api_key,
    load_user_profile as _load_user_profile,
    register_user as _register_user,
    save_progress,
    save_user_ai_config as _save_user_ai_config,
    save_user_api_key as _save_user_api_key,
    save_user_profile as _save_user_profile,
)


def parse_json_response(response_text: str) -> Dict[str, Any]:
    if not response_text:
        return {"error": "空响应"}
    try:
        parsed_data = json.loads(response_text)
        if isinstance(parsed_data, dict) and "error" in parsed_data:
            st.error(f"解析错误: {parsed_data['error']}")
        return parsed_data
    except json.JSONDecodeError:
        pass
    try:
        cleaned_text = response_text.strip()
        cleaned_text = re.sub(r'```json\s*', '', cleaned_text)
        cleaned_text = re.sub(r'```\s*', '', cleaned_text)
        cleaned_text = cleaned_text.strip()
        cleaned_text = re.sub(r'\'(\w+)\'\s*:', '"\1":', cleaned_text)
        cleaned_text = re.sub(r':\s*\'(.*?)\'', ': "\1"', cleaned_text)
        cleaned_text = re.sub(r',\s*}', '}', cleaned_text)
        start_index = cleaned_text.find('{')
        end_index = cleaned_text.rfind('}')
        if start_index != -1 and end_index != -1 and start_index < end_index:
            json_str = cleaned_text[start_index:end_index + 1]
            parsed_data = json.loads(json_str)
            return parsed_data
        if cleaned_text.startswith('[') and cleaned_text.endswith(']'):
            parsed_data = json.loads(cleaned_text)
            return {"data": parsed_data}
    except Exception as e:
        st.warning(f"JSON解析失败: {str(e)}")
    return {"raw_text": response_text, "formatted_text": response_text}


def validate_essay_length(essay_content: str, min_words: int = 150, max_words: int = 300) -> Tuple[bool, str]:
    if not essay_content or essay_content.strip() == "":
        return False, "作文内容为空"
    words = re.findall(r'[a-zA-Z]+|[\u4e00-\u9fff]', essay_content)
    word_count = len(words)
    if word_count < min_words:
        return False, f"作文字数不足（{word_count}字），建议至少写{min_words}字"
    elif word_count > max_words:
        return False, f"作文字数超过限制（{word_count}字），建议控制在{max_words}字以内"
    else:
        return True, f"字数合适（{word_count}字）"


def create_score_gauge(score: float, max_score: float = 9.0) -> str:
    if score >= 7.0:
        color = "🟢"
        level = "优秀"
        emoji = "🎉"
    elif score >= 6.0:
        color = "🟡"
        level = "良好"
        emoji = "👍"
    elif score >= 5.0:
        color = "🟠"
        level = "及格"
        emoji = "✅"
    else:
        color = "🔴"
        level = "需提高"
        emoji = "💪"
    return f"{color} {score:.1f}/9.0 {emoji} ({level})"


def get_score_color(score: float) -> str:
    if score >= 7.0:
        return "green"
    elif score >= 6.0:
        return "orange"
    elif score >= 5.0:
        return "yellow"
    else:
        return "red"


def calculate_band_score(scores: Dict[str, float]) -> float:
    if not scores:
        return 0.0
    total = sum(scores.values())
    average = total / len(scores)
    decimal = average - int(average)
    if decimal >= 0.75:
        return int(average) + 1.0
    elif decimal >= 0.25:
        return int(average) + 0.5
    else:
        return int(average) + 0.0


def extract_feedback_sections(feedback_text: str) -> Dict[str, str]:
    sections = {
        "task_achievement": "",
        "coherence_cohesion": "",
        "lexical_resource": "",
        "grammatical_range_accuracy": "",
        "overall_feedback": ""
    }
    patterns = {
        "task_achievement": r"(任务完成度|任务回应).*?((?=\n[A-Z]|\n[#]|$))",
        "coherence_cohesion": r"(连贯与衔接|文章结构).*?((?=\n[A-Z]|\n[#]|$))",
        "lexical_resource": r"(词汇资源|词汇使用).*?((?=\n[A-Z]|\n[#]|$))",
        "grammatical_range_accuracy": r"(语法范围|语法准确性).*?((?=\n[A-Z]|\n[#]|$))",
        "overall_feedback": r"(总体反馈|总结建议).*?((?=\n[A-Z]|\n[#]|$))"
    }
    for section, pattern in patterns.items():
        match = re.search(pattern, feedback_text, re.IGNORECASE | re.DOTALL)
        if match:
            sections[section] = match.group(2).strip() if match.group(2) else match.group(0).strip()
    return sections


def format_speaking_time(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}秒"
    else:
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        return f"{minutes}分{remaining_seconds}秒"


def _round_to_ielts_score(score: float) -> float:
    score = max(0.0, min(9.0, float(score)))
    whole = int(score)
    decimal = score - whole
    if decimal < 0.25:
        return float(whole)
    if decimal < 0.75:
        return whole + 0.5
    return min(9.0, whole + 1.0)


def generate_study_plan(current_level: float, target_score: float, weeks: int = 12) -> Dict[str, Any]:
    current_level = _round_to_ielts_score(current_level)
    target_score = _round_to_ielts_score(target_score)
    score_gap = target_score - current_level
    intensity = "中等" if score_gap <= 1.0 else "高强度"
    plan = {
        "current_level": current_level,
        "target_score": target_score,
        "study_weeks": weeks,
        "intensity": intensity,
        "weekly_schedule": [],
        "focus_areas": []
    }
    if score_gap > 1.0:
        plan["focus_areas"] = ["基础语法", "核心词汇", "基本句型"]
    elif score_gap > 0.5:
        plan["focus_areas"] = ["流利度", "词汇多样性", "复杂句型"]
    else:
        plan["focus_areas"] = ["答题技巧", "时间管理", "高级表达"]
    for week in range(1, weeks + 1):
        weekly_plan = {"week": week, "focus": "", "tasks": [], "goals": []}
        if week <= 4:
            weekly_plan["focus"] = "基础巩固"
            weekly_plan["tasks"] = ["每天背诵50个核心词汇", "完成2篇作文练习", "进行3次口语录音练习"]
        elif week <= 8:
            weekly_plan["focus"] = "技能提升"
            weekly_plan["tasks"] = ["重点练习弱项领域", "模拟考试环境练习", "分析范文结构"]
        else:
            weekly_plan["focus"] = "冲刺阶段"
            weekly_plan["tasks"] = ["全真模拟测试", "错题回顾分析", "时间管理训练"]
        weekly_target = _round_to_ielts_score(current_level + (week / weeks) * score_gap)
        weekly_plan["goals"] = [f"目标分数提升到{weekly_target:.1f}"]
        plan["weekly_schedule"].append(weekly_plan)
    return plan


def save_user_progress(user_id: str, activity: str, data: Dict[str, Any]):
    try:
        if is_mysql_configured():
            save_progress(user_id, activity, data)
            return
        if "user_progress" not in st.session_state:
            st.session_state.user_progress = []
        progress_record = {
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "activity": activity,
            "data": data
        }
        st.session_state.user_progress.append(progress_record)
        if len(st.session_state.user_progress) > 100:
            st.session_state.user_progress = st.session_state.user_progress[-100:]
    except Exception as e:
        print(f"保存进度时出错: {e}")


def get_user_progress(user_id: str) -> List[Dict[str, Any]]:
    if is_mysql_configured():
        try:
            return get_progress(user_id)
        except Exception as e:
            print(f"获取数据库进度时出错，回退到内存记录: {e}")
    if "user_progress" not in st.session_state:
        return []
    return [r for r in st.session_state.user_progress if r.get("user_id") == user_id]


def save_user_profile(user_id: str, profile: Dict[str, Any]) -> bool:
    profile = {**profile, "user_id": user_id}
    st.session_state.user_profile = profile
    if not is_mysql_configured():
        return False
    try:
        _save_user_profile(user_id, profile)
        return True
    except Exception as e:
        print(f"保存用户档案时出错: {e}")
        return False


def load_user_profile(user_id: str) -> Dict[str, Any] | None:
    if not is_mysql_configured():
        return None
    try:
        return _load_user_profile(user_id)
    except Exception as e:
        print(f"读取用户档案时出错: {e}")
        return None


def authenticate_user(user_id: str, password: str) -> bool:
    try:
        return _authenticate_user(user_id, password)
    except Exception as e:
        print(f"用户认证时出错: {e}")
        return False


def register_user(user_id: str, password: str) -> bool:
    try:
        return _register_user(user_id, password)
    except Exception as e:
        print(f"用户注册时出错: {e}")
        return False


def initialize_database():
    try:
        return _initialize_database()
    except Exception as e:
        print(f"数据库初始化时出错: {e}")
        return False


def get_database_status():
    try:
        return _get_database_status()
    except Exception as e:
        return {"status": "error", "message": str(e)}


def create_progress_chart_data(progress_data: List[Dict[str, Any]]) -> pd.DataFrame:
    dates = []
    scores = []
    activities = []
    for record in progress_data:
        try:
            timestamp = record.get("timestamp", "")
            if timestamp:
                dt = datetime.fromisoformat(timestamp)
                dates.append(dt.strftime("%m/%d"))
            else:
                dates.append("")
            score = record.get("score")
            if score is not None:
                scores.append(float(score))
            elif "data" in record and isinstance(record["data"], dict) and "score" in record["data"]:
                scores.append(float(record["data"]["score"]))
            else:
                scores.append(0)
            activities.append(record.get("activity", ""))
        except:
            continue
    return pd.DataFrame({"date": dates, "score": scores, "activity": activities})


def calculate_estimated_study_time(target_score: float, current_level: float) -> Dict[str, Any]:
    score_gap = target_score - current_level
    if score_gap <= 0.5:
        total_hours = 40
        recommended_weeks = 4
    elif score_gap <= 1.0:
        total_hours = 80
        recommended_weeks = 8
    elif score_gap <= 1.5:
        total_hours = 120
        recommended_weeks = 12
    else:
        total_hours = 200
        recommended_weeks = 20
    return {
        "score_gap": score_gap,
        "total_hours": total_hours,
        "recommended_weeks": recommended_weeks,
        "weekly_hours": total_hours / recommended_weeks,
        "daily_hours": total_hours / (recommended_weeks * 7)
    }


# ============================================================
# 跨版本共享工具（app_web.py + main.py 共用）
# ============================================================

def cross_login_token(user_id):
    secret = os.getenv("FLASK_SECRET_KEY", "ielts_cross_login_secret_2024")
    return hmac.new(secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()[:16]



def verify_cross_token(user_id, token):
    if not user_id or not token:
        return False
    return hmac.compare_digest(cross_login_token(user_id), token)


def simple_md_filter(text):
    """将简易 Markdown 转为 HTML（不依赖 Flask/Streamlit）"""
    if not text:
        return ""
    out = str(text)
    out = out.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    lines = out.split('\n')
    result_lines = []
    in_ul = False
    in_ol = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_ul:
                result_lines.append('</ul>')
                in_ul = False
            if in_ol:
                result_lines.append('</ol>')
                in_ol = False
            result_lines.append('')
            continue
        m3 = re.match(r'^#{3,}\s+(.+)$', stripped)
        m2 = re.match(r'^##\s+(.+)$', stripped)
        m1 = re.match(r'^#\s+(.+)$', stripped)
        if m3:
            if in_ul: result_lines.append('</ul>'); in_ul = False
            if in_ol: result_lines.append('</ol>'); in_ol = False
            result_lines.append('<h4>' + m3.group(1) + '</h4>')
            continue
        if m2:
            if in_ul: result_lines.append('</ul>'); in_ul = False
            if in_ol: result_lines.append('</ol>'); in_ol = False
            result_lines.append('<h3>' + m2.group(1) + '</h3>')
            continue
        if m1:
            if in_ul: result_lines.append('</ul>'); in_ul = False
            if in_ol: result_lines.append('</ol>'); in_ol = False
            result_lines.append('<h2>' + m1.group(1) + '</h2>')
            continue
        ul_match = re.match(r'^[-*]\s+(.+)$', stripped)
        if ul_match:
            if in_ol: result_lines.append('</ol>'); in_ol = False
            if not in_ul: result_lines.append('<ul>'); in_ul = True
            result_lines.append('<li>' + ul_match.group(1) + '</li>')
            continue
        ol_match = re.match(r'^\d+[.)]\s+(.+)$', stripped)
        if ol_match:
            if in_ul: result_lines.append('</ul>'); in_ul = False
            if not in_ol: result_lines.append('<ol>'); in_ol = True
            result_lines.append('<li>' + ol_match.group(1) + '</li>')
            continue
        if in_ul: result_lines.append('</ul>'); in_ul = False
        if in_ol: result_lines.append('</ol>'); in_ol = False
        result_lines.append(stripped)
    if in_ul: result_lines.append('</ul>')
    if in_ol: result_lines.append('</ol>')
    out = '\n'.join(result_lines)
    out = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', out)
    out = re.sub(r'`([^`]+)`', r'<code>\1</code>', out)
    out = re.sub(r'(?<!\n)\n(?!\n)', '<br>', out)
    out = re.sub(r'\n\n+', '</p><p>', out)
    out = '<p>' + out + '</p>'
    out = out.replace('<p></p>', '').replace('<p><h2>', '<h2>').replace('</h2></p>', '</h2>')
    out = out.replace('<p><h3>', '<h3>').replace('</h3></p>', '</h3>')
    out = out.replace('<p><h4>', '<h4>').replace('</h4></p>', '</h4>')
    out = out.replace('<p><ul>', '<ul>').replace('</ul></p>', '</ul>')
    out = out.replace('<p><ol>', '<ol>').replace('</ol></p>', '</ol>')
    out = out.replace('<p><li>', '<li>').replace('</li></p>', '</li>')
    return out


def build_task1_chart_assets(result_data, raw_text=""):
    if not isinstance(result_data, dict) or result_data.get("task_type") != "Task 1":
        return result_data
    data = dict(result_data)
    chart_type = data.get("chart_type") or "柱状图"

    # 尝试从 raw_text 中提取 chart_labels 和 chart_data
    if not data.get("chart_data") and raw_text:
        labels_match = re.search(r'\*\*chart_labels：\*\*\s*(\[.*?\])\s*\n', raw_text)
        data_match = re.search(r'\*\*chart_data：\*\*\s*(\[.*?\])\s*\n', raw_text, re.DOTALL)
        if labels_match:
            try:
                data["chart_labels"] = json.loads(labels_match.group(1))
            except Exception:
                pass
        if data_match:
            try:
                data["chart_data"] = json.loads(data_match.group(1))
            except Exception:
                pass

    labels = data.get("chart_labels") or []
    # 当 AI 提供了 chart_data 但没提供 chart_labels 时，从 data 提取
    if not labels and data.get("chart_data"):
        labels = [item.get("label", f"项{i+1}") for i, item in enumerate(data["chart_data"])]

    # 智能 fallback — 随机选一组标签
    if not labels:
        fallback_sets = [
            ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"],
            ["Spring", "Summer", "Autumn", "Winter"],
            ["2018", "2019", "2020", "2021", "2022", "2023"],
            ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        ]
        labels = random.choice(fallback_sets)

    if not data.get("chart_data"):
        base = random.randint(20, 55)
        values = [max(5, min(95, base + random.randint(-8, 18) + i * random.randint(2, 7))) for i in range(len(labels))]
        data["chart_data"] = [{"label": label, "value": value} for label, value in zip(labels, values)]

    data["chart_labels"] = labels
    image_dir = os.path.join(os.path.dirname(__file__), "data", "charts")
    os.makedirs(image_dir, exist_ok=True)
    filename = f"task1_{uuid.uuid4().hex[:10]}.png"
    path = os.path.join(image_dir, filename)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        table = data["chart_data"]
        x_labels = [str(item.get("label", "")) for item in table]
        y_values = [float(item.get("value", 0)) for item in table]
        fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=140)
        colors = ["#0f7b63", "#e67e22", "#3498db", "#9b59b6", "#e74c3c", "#1abc9c", "#f39c12", "#2ecc71"]
        if "线" in chart_type:
            ax.plot(x_labels, y_values, marker="o", linewidth=2.4, color="#0f7b63")
        elif "饼" in chart_type or len(x_labels) <= 2:
            ax.pie(y_values, labels=x_labels, autopct="%1.0f%%", startangle=90, colors=colors[:len(x_labels)])
            ax.axis("equal")
        else:
            bars = ax.bar(x_labels, y_values, color=[colors[i % len(colors)] for i in range(len(x_labels))])
        ax.set_title(data.get("question", "IELTS Task 1 Chart")[:90], fontsize=11)
        if "饼" not in chart_type and len(x_labels) > 2:
            ax.set_ylabel("Value")
            ax.grid(axis="y", alpha=0.25)
            if len(x_labels) > 8:
                plt.xticks(rotation=45, ha="right")
        fig.tight_layout()
        fig.savefig(path, dpi=140)
        plt.close(fig)
        data["chart_image"] = f"data/charts/{filename}"
    except Exception:
        data["chart_image"] = ""
    return data


def parse_model_output(raw):
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def parse_generated_topic_md(raw_text, task_type="Task 2"):
    """从 AI 输出的 Markdown 格式中提取作文题目结构化数据"""
    result = {"task_type": task_type, "question": ""}
    if not raw_text:
        return result

    # 提取 question（**题目：** ... 后面的内容）
    q_match = re.search(r'\*\*题目：\*\*\s*(.+?)(?:\n\*\*|\Z)', raw_text, re.DOTALL)
    if q_match:
        result["question"] = q_match.group(1).strip()

    if task_type == "Task 1":
        ct = re.search(r'\*\*图表类型：\*\*\s*(.+?)(?:\n|$)', raw_text)
        if ct:
            result["chart_type"] = ct.group(1).strip()

        lbs = re.search(r'\*\*chart_labels：\*\*\s*(\[.*?\])\s*', raw_text)
        if lbs:
            try:
                result["chart_labels"] = json.loads(lbs.group(1))
            except Exception:
                pass

        cd = re.search(r'\*\*chart_data：\*\*\s*(\[.*?\])\s*(?:\n\*\*|\Z)', raw_text, re.DOTALL)
        if cd:
            try:
                result["chart_data"] = json.loads(cd.group(1))
            except Exception:
                pass

        kf = re.search(r'\*\*关键特征：\*\*\s*((?:- .+\n?)+)', raw_text)
        if kf:
            result["key_features"] = [x.strip("- ").strip() for x in kf.group(1).strip().split("\n") if x.strip().startswith("-")]

        ss = re.search(r'\*\*建议结构：\*\*\s*(.+?)(?:\n\*\*|\Z)', raw_text)
        if ss:
            result["suggested_structure"] = ss.group(1).strip()
    else:
        tc = re.search(r'\*\*话题类别：\*\*\s*(.+?)(?:\n|$)', raw_text)
        if tc:
            result["topic_category"] = tc.group(1).strip()

        et = re.search(r'\*\*作文类型：\*\*\s*(.+?)(?:\n|$)', raw_text)
        if et:
            result["essay_type"] = et.group(1).strip()

        kp = re.search(r'\*\*关键论点：\*\*\s*((?:- .+\n?)+)', raw_text)
        if kp:
            result["key_points"] = [x.strip("- ").strip() for x in kp.group(1).strip().split("\n") if x.strip().startswith("-")]

        ss = re.search(r'\*\*建议结构：\*\*\s*(.+?)(?:\n\*\*|\Z)', raw_text)
        if ss:
            result["suggested_structure"] = ss.group(1).strip()

    return result


def learning_record_title(activity: str) -> str:
    """根据 activity 内容返回语义化的标题"""
    if not activity:
        return "学习记录详情"
    if any(kw in activity for kw in ["题目生成", "生成作文题目", "作文题目"]):
        return "当时生成的题目"
    if any(kw in activity for kw in ["思路互动", "思路", "写作思路", "ideas"]):
        return "写作思路参考"
    if any(kw in activity for kw in ["参考范文", "范文"]):
        return "参考范文"
    if any(kw in activity for kw in ["串题"]):
        return "串题方案"
    if any(kw in activity for kw in ["批改", "口语反馈", "feedback"]):
        return "批改结果 / 反馈"
    return "学习记录详情"


# ============================================================
# AI 配置 API 公共包装（database 层转发）
# ============================================================


def load_user_ai_config(user_id):
    return _load_user_ai_config(user_id)


def save_user_ai_config(user_id, provider=None, api_key=None, model=None, base_url=None):
    return _save_user_ai_config(user_id, provider, api_key, model, base_url)



def load_user_api_key(user_id):
    return _load_user_api_key(user_id)


def save_user_api_key(user_id, api_key):
    return _save_user_api_key(user_id, api_key)
