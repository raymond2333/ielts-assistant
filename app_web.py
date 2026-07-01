import hmac
import html
import hashlib
import json
import os
import random
import re
import uuid
from datetime import datetime
from difflib import SequenceMatcher
from functools import lru_cache, wraps
from importlib.util import find_spec
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
    get_latest_progress_by_activity,
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

STUDY_PLAN_ACTIVITY = "学习计划"
IMPROVEMENT_SUGGESTIONS_ACTIVITY = "重点提升建议"


def build_task1_chart_assets(result_data, raw_text=""):
    return _build_task1_chart_assets(result_data, raw_text)


@app.template_filter("simple_md")
def simple_md_filter(text):
    return Markup(_simple_md_filter(text))


@app.template_filter("record_title")
def record_title_filter(activity):
    return learning_record_title(activity)


@app.template_filter("beijing_time")
def beijing_time_filter(value):
    """Format ISO datetime string to Beijing time in readable format."""
    if not value:
        return ""
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    _BJ = _tz(_td(hours=8))
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return ""
        try:
            dt = _dt.fromisoformat(value)
        except (ValueError, TypeError):
            return value
    else:
        dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_BJ)
    else:
        dt = dt.astimezone(_BJ)
    return dt.strftime("%Y年%m月%d日 %H:%M")


def _html_list(items):
    if not items:
        return ""
    if isinstance(items, str):
        return f"<p>{escape(items)}</p>"
    return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"


def score_encouragement_html(score):
    try:
        score = float(score)
    except (TypeError, ValueError):
        return ""
    if score >= 7.5:
        label, text = "excellent", "太棒了，这已经很接近高分表达了！继续保持表达的深度和准确度。"
    elif score >= 6.5:
        label, text = "good", "真棒，已经达到 6.5+ 的关键门槛了！再打磨词汇和连贯性会更稳。"
    elif score >= 5.5:
        label, text = "steady", "不错，基础表达已经站住了。下一步重点把答案展开得更具体。"
    else:
        label, text = "warm", "别急，这次练习很有价值。先把回答说完整，再逐步提升词汇和语法。"
    return f"<div class='score-encouragement {label}'>{escape(text)}</div>"


def _audio_html(audio_file):
    if not audio_file:
        return ""
    audio_type = "audio/webm" if str(audio_file).endswith(".webm") else "audio/mp4"
    return (
        "<p><strong>录音回放：</strong></p>"
        "<audio controls preload='none' style='width:100%;max-width:360px'>"
        f"<source src='/{escape(audio_file)}' type='{audio_type}'>"
        "</audio>"
    )


def _feedback_html(feedbacks):
    if not feedbacks:
        return ""
    blocks = []
    for index, feedback in enumerate(feedbacks, 1):
        data = feedback.get("result_data") if isinstance(feedback, dict) else None
        data = data if isinstance(data, dict) else {}
        body = []
        if feedback.get("timestamp"):
            body.append(f"<p class='record-meta'><strong>反馈时间：</strong>{escape(beijing_time_filter(feedback['timestamp']))}</p>")
        if feedback.get("audio_file"):
            body.append(_audio_html(feedback.get("audio_file")))
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

    if result_data.get("overall_score") is not None and isinstance(result_data.get("breakdown"), dict):
        sections.append(score_encouragement_html(result_data.get("overall_score")))
        sections.append(
            "<details class='result-accordion' open><summary>总体评分</summary>"
            f"<div class='result-body'><p><strong>总分：</strong>{escape(result_data.get('overall_score'))} / 9.0</p></div></details>"
        )
        breakdown_labels = {
            "fluency_coherence": "流利度与连贯性",
            "lexical_resource": "词汇资源",
            "grammatical_range_accuracy": "语法范围与准确性",
            "pronunciation": "发音",
        }
        feedback_labels = {
            "score": "分数",
            "strengths": "优点",
            "weaknesses": "待改进",
            "suggestions": "建议",
            "vocabulary_analysis": "词汇分析",
            "suggested_words": "推荐词汇",
            "grammar_analysis": "语法分析",
            "common_errors": "常见错误",
            "pronunciation_analysis": "发音分析",
            "improvement_tips": "改进建议",
        }
        for key, item in result_data.get("breakdown", {}).items():
            if not isinstance(item, dict):
                continue
            label = breakdown_labels.get(key, key)
            score = item.get("score", "")
            body = []
            for sub_key, value in item.items():
                if value in (None, "", [], {}):
                    continue
                sub_label = feedback_labels.get(sub_key, sub_key)
                if isinstance(value, list):
                    body.append(f"<p><strong>{escape(sub_label)}：</strong></p>{_html_list(value)}")
                else:
                    body.append(f"<p><strong>{escape(sub_label)}：</strong>{escape(value)}</p>")
            if body:
                sections.append(
                    f"<details class='result-accordion'><summary>{escape(label)}{f' · {escape(score)}' if score else ''}</summary>"
                    f"<div class='result-body'>{''.join(body)}</div></details>"
                )
        if result_data.get("improved_response"):
            sections.append(
                "<details class='result-accordion'><summary>优化回答示例</summary>"
                f"<div class='result-body'><p>{escape(result_data['improved_response'])}</p></div></details>"
            )
        if result_data.get("practice_recommendations"):
            sections.append(
                "<details class='result-accordion'><summary>练习建议</summary>"
                f"<div class='result-body'>{_html_list(result_data['practice_recommendations'])}</div></details>"
            )
        return Markup("".join(sections))

    if result_data.get("unifying_theme") or isinstance(result_data.get("linked_responses"), list):
        theme_body = []
        if result_data.get("unifying_theme"):
            theme_body.append(f"<p><strong>中文：</strong>{escape(result_data['unifying_theme'])}</p>")
        if result_data.get("unifying_theme_en"):
            theme_body.append(f"<p><strong>English：</strong>{escape(result_data['unifying_theme_en'])}</p>")
        if theme_body:
            sections.append(
                "<details class='result-accordion' open><summary>核心主题</summary>"
                f"<div class='result-body'>{''.join(theme_body)}</div></details>"
            )

        linked_responses = result_data.get("linked_responses") or []
        if isinstance(linked_responses, list):
            for index, item in enumerate(linked_responses, 1):
                if not isinstance(item, dict):
                    continue
                title = item.get("topic") or f"话题 {index}"
                if item.get("topic_en"):
                    title = f"{title} / {item.get('topic_en')}"
                body = []
                if item.get("adapted_response"):
                    body.append(f"<p><strong>中文方案：</strong>{escape(item['adapted_response'])}</p>")
                if item.get("adapted_response_en"):
                    english = str(item["adapted_response_en"])
                    body.append(
                        "<p><strong>English Response：</strong>"
                        "<button class='speak-btn' type='button'>朗读答案</button></p>"
                        f"<p class='speak-source'>{escape(english)}</p>"
                    )
                if item.get("possible_questions"):
                    body.append("<p><strong>可能出现的相关考题：</strong></p>")
                    body.append(_html_list(item["possible_questions"]))
                if item.get("key_elements"):
                    body.append("<p><strong>关键元素：</strong></p>")
                    body.append(_html_list(item["key_elements"]))
                if item.get("transition_phrases"):
                    body.append("<p><strong>过渡短语：</strong></p>")
                    body.append(_html_list(item["transition_phrases"]))
                sections.append(
                    f"<details class='result-accordion nested-answer' {'open' if index == 1 else ''}>"
                    f"<summary>话题 {index}：{escape(title)}</summary>"
                    f"<div class='result-body'>{''.join(body)}</div></details>"
                )

        if result_data.get("versatile_vocabulary") or result_data.get("versatile_vocabulary_en"):
            vocab_body = []
            if result_data.get("versatile_vocabulary"):
                vocab_body.append("<p><strong>中文：</strong></p>")
                vocab_body.append(_html_list(result_data["versatile_vocabulary"]))
            if result_data.get("versatile_vocabulary_en"):
                vocab_body.append("<p><strong>English：</strong></p>")
                vocab_body.append(_html_list(result_data["versatile_vocabulary_en"]))
            sections.append(
                "<details class='result-accordion'><summary>通用词汇</summary>"
                f"<div class='result-body'>{''.join(vocab_body)}</div></details>"
            )
        if result_data.get("practice_strategy"):
            sections.append(
                "<details class='result-accordion'><summary>练习策略</summary>"
                f"<div class='result-body'><p>{escape(result_data['practice_strategy'])}</p></div></details>"
            )
        if result_data.get("study_plan"):
            sections.append(
                "<details class='result-accordion'><summary>学习计划</summary>"
                f"<div class='result-body'><p>{escape(result_data['study_plan'])}</p></div></details>"
            )
        return Markup("".join(sections))

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
                    f"<div class='result-body'><button class='speak-btn' type='button'>朗读参考答案</button><p class='speak-source'>{escape(item['model_answer'])}</p></div></details>"
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
                    f"<div class='result-body'><button class='speak-btn' type='button'>朗读参考答案</button><p class='speak-source'>{escape(item['model_response'])}</p></div></details>"
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
                speak_html = f"<button class='speak-btn' type='button'>朗读参考答案</button><div class='speak-source' hidden>{escape(speak_text)}</div>"
            sections.append(
                "<details class='result-accordion'><summary>参考答案</summary>"
                f"<div class='result-body'>{speak_html}{''.join(body)}</div></details>"
            )

    elif isinstance(model_answer, str) and model_answer.strip():
        sections.append(
            "<details class='result-accordion'><summary>参考答案</summary>"
            f"<div class='result-body'><button class='speak-btn' type='button'>朗读参考答案</button><p class='speak-source'>{escape(model_answer)}</p></div></details>"
        )

    criteria_labels = {
        "task_achievement": "任务完成度",
        "task_response": "任务回应",
        "coherence_cohesion": "连贯与衔接",
        "lexical_resource": "词汇资源",
        "grammatical_range": "语法多样性与准确性",
        "grammatical_range_accuracy": "语法范围与准确性",
    }
    sub_labels = {
        "score": "分数",
        "comments": "评价",
        "assessment": "评价",
        "grammar_analysis": "语法分析",
        "strengths": "优点",
        "improvements": "改进建议",
        "errors": "问题",
        "suggestions": "建议",
        "examples": "示例",
    }
    for key, label in criteria_labels.items():
        item = result_data.get(key)
        if not isinstance(item, dict):
            continue
        summary = label
        if item.get("score") is not None:
            summary = f"{label} · {escape(item['score'])}"
        body = []
        for sub_key, value in item.items():
            if value in (None, "", [], {}):
                continue
            sub_label = sub_labels.get(sub_key, sub_key)
            if isinstance(value, list):
                body.append(f"<p><strong>{escape(sub_label)}：</strong></p>{_html_list(value)}")
            elif isinstance(value, dict):
                nested = "".join(
                    f"<li><strong>{escape(str(k))}：</strong>{escape(str(v))}</li>"
                    for k, v in value.items()
                    if v not in (None, "", [], {})
                )
                if nested:
                    body.append(f"<p><strong>{escape(sub_label)}：</strong></p><ul>{nested}</ul>")
            else:
                content = escape(str(value))
                body.append(f"<p><strong>{escape(sub_label)}：</strong>{content}</p>")
        if body:
            sections.append(
                f"<details class='result-accordion'><summary>{summary}</summary>"
                f"<div class='result-body'>{''.join(body)}</div></details>"
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
                speak_html = f"<button class='speak-btn' type='button'>朗读答案</button><div class='speak-source' hidden>{escape(value)}</div>"
            sections.append(
                f"<details class='result-accordion'><summary>{label}</summary>"
                f"<div class='result-body'>{speak_html}{content}</div></details>"
            )

    if not sections:
        sections.append(f"<pre>{escape(json.dumps(result_data, ensure_ascii=False, indent=2))}</pre>")

    return Markup("".join(sections))


@app.template_filter("study_plan_result")
def study_plan_result_filter(plan):
    if not plan:
        return Markup("")
    if isinstance(plan, str):
        parsed = parse_model_output(plan)
        if isinstance(parsed, dict) and "formatted_text" not in parsed:
            plan = parsed
        else:
            return Markup(simple_md_filter(plan))
    if not isinstance(plan, dict):
        return Markup(f"<pre>{escape(str(plan))}</pre>")

    sections = []
    if plan.get("overall_assessment"):
        sections.append(
            "<details class='result-accordion' open><summary>总体评价</summary>"
            f"<div class='result-body'><p>{escape(plan['overall_assessment'])}</p></div></details>"
        )
    if plan.get("priority_areas"):
        sections.append(
            "<details class='result-accordion'><summary>优先提升领域</summary>"
            f"<div class='result-body'>{_html_list(plan['priority_areas'])}</div></details>"
        )
    weekly = plan.get("weekly_schedule")
    if isinstance(weekly, list):
        week_blocks = []
        for item in weekly:
            if not isinstance(item, dict):
                continue
            week = escape(item.get("week", ""))
            theme = escape(item.get("theme", ""))
            body = []
            if item.get("focus"):
                body.append(f"<p><strong>重点：</strong>{escape(item['focus'])}</p>")
            if item.get("tasks"):
                body.append("<p><strong>具体任务：</strong></p>")
                body.append(_html_list(item["tasks"]))
            if item.get("goal"):
                body.append(f"<p><strong>本周目标：</strong>{escape(item['goal'])}</p>")
            week_blocks.append(
                f"<details class='result-accordion nested-answer'><summary>第 {week} 周：{theme}</summary>"
                f"<div class='result-body'>{''.join(body)}</div></details>"
            )
        sections.append(
            "<details class='result-accordion' open><summary>每周安排</summary>"
            f"<div class='result-body'>{''.join(week_blocks)}</div></details>"
        )
    if plan.get("study_tips"):
        sections.append(
            "<details class='result-accordion'><summary>学习建议</summary>"
            f"<div class='result-body'>{_html_list(plan['study_tips'])}</div></details>"
        )
    if plan.get("milestones"):
        sections.append(
            "<details class='result-accordion'><summary>阶段检查点</summary>"
            f"<div class='result-body'>{_html_list(plan['milestones'])}</div></details>"
        )
    if not sections:
        sections.append(f"<pre>{escape(json.dumps(plan, ensure_ascii=False, indent=2))}</pre>")
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


def int_query(name, default=1):
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


def paginate_records(records, page, per_page=10):
    total = len(records)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    return records[start:start + per_page], page, total_pages, total


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


def local_transcribe_available():
    return find_spec("faster_whisper") is not None


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


def _normalized_answer_text(text):
    text = str(text or "").lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    return " ".join(text.split())


def _flatten_reference_answer(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_flatten_reference_answer(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_flatten_reference_answer(item) for item in value.values())
    return ""


def collect_reference_answers(parent_data, source_mode):
    if not isinstance(parent_data, dict):
        return []
    answers = []
    if source_mode == "part1":
        for item in parent_data.get("questions", []):
            if isinstance(item, dict) and item.get("model_answer"):
                answers.append(item["model_answer"])
    elif source_mode == "part2":
        answer = _flatten_reference_answer(parent_data.get("model_answer"))
        if answer:
            answers.append(answer)
    elif source_mode == "part3":
        for item in parent_data.get("discussion_questions", []):
            if isinstance(item, dict) and item.get("model_response"):
                answers.append(item["model_response"])
    return [answer for answer in answers if _normalized_answer_text(answer)]


def reference_answer_note_for_submission(user_response, parent_data, source_mode):
    response = _normalized_answer_text(user_response)
    if len(response) < 40:
        return "无"
    for answer in collect_reference_answers(parent_data, source_mode):
        reference = _normalized_answer_text(answer)
        if len(reference) < 40:
            continue
        shorter = min(len(response), len(reference))
        contains = shorter >= 40 and (response in reference or reference in response)
        similarity = SequenceMatcher(None, response, reference).ratio()
        if contains or similarity >= 0.88:
            return (
                "考生回答与本题系统生成的 Band 8.0-8.5 高分参考答案高度一致。"
                "请按高分参考答案的语言质量评分，不要无依据压到 5.0-6.0。"
            )
    return "无"


def is_speaking_feedback_record(record):
    data = record.get("data") if isinstance(record, dict) else {}
    return record.get("activity") == "口语反馈" or (isinstance(data, dict) and data.get("mode") == "speaking_feedback")


def is_attachable_speaking_feedback(record):
    data = record.get("data") if isinstance(record, dict) else {}
    return is_speaking_feedback_record(record) or (
        isinstance(data, dict)
        and data.get("mode") == "speaking_recording"
        and data.get("result_data")
    )


def feedback_result_data_with_score(result_data, score):
    if isinstance(result_data, dict) and result_data.get("overall_score") not in (None, ""):
        return result_data
    if isinstance(result_data, dict) and score not in (None, ""):
        result_data = dict(result_data)
        result_data["overall_score"] = score
    return result_data


def canonical_feedback_score(result_data, fallback_score=None):
    if isinstance(result_data, dict):
        normalized = normalize_ielts_score(result_data.get("overall_score"))
        if normalized is not None:
            return normalized
    normalized = normalize_ielts_score(fallback_score)
    return normalized


def inline_speaking_feedback_html(inline):
    inline = inline if isinstance(inline, dict) else {}
    result_data = inline.get("result_data")
    score = canonical_feedback_score(result_data, inline.get("score"))
    title = "本题 AI 批改反馈"
    body = []
    if inline.get("recorded_at"):
        body.append(f"<p class='record-meta'><strong>训练时间：</strong>{escape(beijing_time_filter(inline['recorded_at']))}</p>")
    if inline.get("audio_file"):
        body.append(_audio_html(inline.get("audio_file")))
    transcript = inline.get("transcript") or ""
    user_response = inline.get("user_response") or ""
    if transcript:
        body.append(
            "<details class='result-accordion nested-answer' open><summary>转写文本 / 我的回答</summary>"
            f"<div class='result-body'><p>{escape(transcript)}</p></div></details>"
        )
    elif user_response:
        body.append(
            "<details class='result-accordion nested-answer' open><summary>我的回答</summary>"
            f"<div class='result-body'><p>{escape(user_response)}</p></div></details>"
        )
    elif inline.get("audio_file"):
        body.append(
            "<details class='result-accordion nested-answer' open><summary>转写文本</summary>"
            "<div class='result-body'><p class='empty-text'>暂未识别到转写文本。</p></div></details>"
        )
    if inline.get("transcript_source"):
        source_label = {"local": "本地转写", "api": "语音 API 转写", "text": "文本提交"}.get(
            inline.get("transcript_source"),
            inline.get("transcript_source"),
        )
        body.append(f"<p class='record-meta'><strong>转写来源：</strong>{escape(source_label)}</p>")
    if score is not None:
        body.append(f"<p class='record-meta'><strong>本次得分：</strong>{escape(score)} / 9.0</p>")
    if isinstance(result_data, dict):
        body.append(str(record_result_filter(result_data, "口语反馈")))
    elif inline.get("result"):
        body.append(str(simple_md_filter(inline.get("result"))))
    return (
        "<details class='result-accordion nested-answer inline-result voice-inline-feedback' "
        "data-feedback-focus='1' open>"
        f"<summary>{title}</summary><div class='result-body'>{''.join(body)}</div></details>"
    )


def attach_speaking_feedback(records):
    feedback_by_question = {}
    for record in records:
        if not is_attachable_speaking_feedback(record):
            continue
        data = record.get("data") or {}
        question_key = _normalized_question(data.get("question", ""))
        if not question_key:
            continue
        raw_score = data.get("score") if data.get("score") not in (None, "") else record.get("score")
        result_data = feedback_result_data_with_score(data.get("result_data"), raw_score)
        score = canonical_feedback_score(result_data, raw_score)
        result_data = feedback_result_data_with_score(result_data, score)
        feedback_by_question.setdefault(question_key, []).append({
            "id": record.get("id"),
            "timestamp": record.get("timestamp", ""),
            "mode": data.get("mode", ""),
            "score": score,
            "user_response": data.get("user_response", "") or data.get("transcript", ""),
            "transcript": data.get("transcript", ""),
            "audio_file": data.get("audio_file", ""),
            "recorded_at": data.get("recorded_at") or record.get("timestamp", ""),
            "transcript_source": data.get("transcript_source", ""),
            "result": data.get("result", ""),
            "result_data": result_data,
        })

    for feedbacks in feedback_by_question.values():
        feedbacks.sort(key=lambda item: (item.get("timestamp") or "", int(item.get("id") or 0)))

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


def latest_feedback_inline(feedbacks):
    if not feedbacks:
        return None
    latest = feedbacks[-1]
    result_data = latest.get("result_data")
    latest_score = (
        result_data.get("overall_score")
        if isinstance(result_data, dict) and result_data.get("overall_score") not in (None, "")
        else latest.get("score")
    )
    return {
        "mode": latest.get("mode") or "speaking_feedback",
        "result": latest.get("result", ""),
        "result_data": latest.get("result_data"),
        "user_response": latest.get("user_response", "") or latest.get("transcript", ""),
        "transcript": latest.get("transcript", ""),
        "audio_file": latest.get("audio_file", ""),
        "recorded_at": latest.get("recorded_at") or latest.get("timestamp", ""),
        "transcript_source": latest.get("transcript_source", ""),
        "score": latest_score,
    }


def decorate_current_speaking_result(user_id, result_data):
    if not isinstance(result_data, dict):
        return result_data
    wrapper = {
        "activity": "当前口语练习",
        "data": {"result_data": result_data},
    }
    attach_speaking_feedback(get_progress(user_id, limit=300) + [wrapper])
    decorated = wrapper["data"]["result_data"]
    if isinstance(decorated.get("questions"), list):
        for item in decorated["questions"]:
            if isinstance(item, dict) and item.get("_feedbacks"):
                item["_inline_result"] = latest_feedback_inline(item["_feedbacks"])
    if isinstance(decorated.get("discussion_questions"), list):
        for item in decorated["discussion_questions"]:
            if isinstance(item, dict) and item.get("_feedbacks"):
                item["_inline_result"] = latest_feedback_inline(item["_feedbacks"])
    if decorated.get("_feedbacks"):
        decorated["_inline_result"] = latest_feedback_inline(decorated["_feedbacks"])
    return decorated


def visible_progress(records):
    return [
        record for record in records
        if record.get("activity") not in {STUDY_PLAN_ACTIVITY, IMPROVEMENT_SUGGESTIONS_ACTIVITY}
        and not is_speaking_feedback_record(record)
    ]


def with_display_scores(records):
    for record in records:
        score = score_from_progress_record(record)
        if score is not None:
            record["display_score"] = score
            data = record.get("data")
            if isinstance(data, dict):
                data["display_score"] = score
    return records


def prepare_progress(records):
    return with_display_scores(visible_progress(attach_speaking_feedback(records)))


def prepare_feedback_context(records):
    return attach_speaking_feedback(records)


def latest_activity_record(records, activity):
    matched = [record for record in records if record.get("activity") == activity]
    if not matched:
        return None
    return max(matched, key=lambda record: record.get("timestamp") or "")


def latest_saved_suggestions(records):
    record = latest_activity_record(records, IMPROVEMENT_SUGGESTIONS_ACTIVITY)
    data = record.get("data", {}) if record else {}
    if not isinstance(data, dict):
        return None
    suggestions = data.get("suggestions") or data.get("result_data")
    if isinstance(suggestions, str):
        suggestions = parse_model_output(suggestions)
    return suggestions if isinstance(suggestions, dict) else None


def latest_saved_study_plan(records):
    record = latest_activity_record(records, STUDY_PLAN_ACTIVITY)
    data = record.get("data", {}) if record else {}
    if not isinstance(data, dict):
        return None
    plan = data.get("plan") or data.get("study_plan") or data.get("result_data")
    if isinstance(plan, str):
        plan = parse_model_output(plan)
    if isinstance(plan, dict):
        return plan
    return data.get("plan_text") or data.get("result") or ""


def profile_weak_areas(profile):
    weak_areas = profile.get("weak_areas", [])
    if isinstance(weak_areas, str):
        try:
            weak_areas = json.loads(weak_areas)
        except (TypeError, ValueError):
            weak_areas = [weak_areas] if weak_areas else []
    return weak_areas


def calculate_study_plan_inputs(profile, progress):
    speaking_scores = []
    writing_scores = []
    for record in progress:
        data = record.get("data", {}) if isinstance(record, dict) else {}
        if not isinstance(data, dict):
            continue
        score = record.get("score") if record.get("score") is not None else data.get("score")
        if score in (None, ""):
            continue
        try:
            score = float(score)
        except (TypeError, ValueError):
            continue
        activity = record.get("activity", "")
        if "口语" in activity:
            speaking_scores.append(score)
        elif "写作" in activity:
            writing_scores.append(score)

    profile_level = float(profile.get("current_level", 5.0))
    avg_speaking = (
        sum(speaking_scores) / len(speaking_scores)
        if speaking_scores else float(profile.get("speaking_level", profile_level))
    )
    avg_writing = (
        sum(writing_scores) / len(writing_scores)
        if writing_scores else float(profile.get("writing_level", profile_level))
    )
    current_level = (avg_speaking + avg_writing) / 2 if (speaking_scores or writing_scores) else profile_level

    try:
        exam_date = profile.get("exam_date") or ""
        study_weeks = max(1, int((datetime.strptime(exam_date, "%Y-%m-%d") - datetime.now()).days / 7)) if exam_date else 12
    except (TypeError, ValueError):
        study_weeks = 12

    weak_areas = []
    if speaking_scores and avg_speaking < float(profile.get("speaking_level", 6.0)):
        weak_areas.append("口语")
    if writing_scores and avg_writing < float(profile.get("writing_level", 6.0)):
        weak_areas.append("写作")
    if not weak_areas:
        weak_areas = profile_weak_areas(profile) or ["口语", "写作"]

    return current_level, study_weeks, weak_areas


def round_ielts_band(value):
    try:
        return max(0.0, min(9.0, round(float(value) * 2) / 2))
    except (TypeError, ValueError):
        return 5.0


def profile_band(profile, key, default=5.0):
    try:
        return float(profile.get(key, default))
    except (TypeError, ValueError):
        return default


def score_from_progress_record(record):
    data = record.get("data", {}) if isinstance(record, dict) else {}
    if not isinstance(data, dict):
        data = {}
    candidates = []
    result_data = data.get("result_data")
    if isinstance(result_data, dict):
        candidates.append(result_data.get("overall_score"))
    candidates.extend([
        data.get("score"),
        record.get("score"),
    ])
    for candidate in candidates:
        if candidate in (None, ""):
            continue
        score = normalize_ielts_score(candidate)
        if score is not None and score > 0:
            return score
    return None


def progress_skill(record):
    data = record.get("data", {}) if isinstance(record, dict) else {}
    data = data if isinstance(data, dict) else {}
    mode = data.get("mode", "")
    activity = record.get("activity", "")
    if mode in {"speaking_feedback", "speaking_recording"} or "口语反馈" in activity or "口语录音" in activity:
        return "speaking"
    if mode in {"task1", "task2"} or "写作 Task" in activity:
        return "writing"
    return ""


def recent_skill_scores(records, skill, limit=5):
    scores = []
    for record in records:
        if progress_skill(record) != skill:
            continue
        score = score_from_progress_record(record)
        if score is not None:
            scores.append(score)
        if len(scores) >= limit:
            break
    return scores


def tracked_profile_from_progress(profile, records, limit=5):
    tracked = dict(profile)
    speaking_scores = recent_skill_scores(records, "speaking", limit)
    writing_scores = recent_skill_scores(records, "writing", limit)
    if speaking_scores:
        tracked["speaking_level"] = round_ielts_band(sum(speaking_scores) / len(speaking_scores))
    if writing_scores:
        tracked["writing_level"] = round_ielts_band(sum(writing_scores) / len(writing_scores))
    tracked["current_level"] = round_ielts_band(
        (
            profile_band(tracked, "listening_level")
            + profile_band(tracked, "speaking_level")
            + profile_band(tracked, "reading_level")
            + profile_band(tracked, "writing_level")
        )
        / 4
    )
    tracked["_tracking"] = {
        "speaking_scores": speaking_scores,
        "writing_scores": writing_scores,
        "recent_limit": limit,
    }
    return tracked


def refresh_user_level_tracking(user_id):
    profile = load_user_profile(user_id) or default_profile(user_id)
    records = get_progress(user_id, limit=120)
    tracked = tracked_profile_from_progress(profile, records)
    if (
        tracked.get("speaking_level") != profile.get("speaking_level")
        or tracked.get("writing_level") != profile.get("writing_level")
        or tracked.get("current_level") != profile.get("current_level")
    ):
        tracked_to_save = dict(tracked)
        tracked_to_save.pop("_tracking", None)
        save_user_profile(user_id, tracked_to_save)
    return tracked


def find_progress_record(user_id, record_id="", timestamp="", limit=500):
    if not record_id and not timestamp:
        return None
    for item in get_progress(user_id, limit=limit):
        if record_id and str(item.get("id")) == str(record_id):
            return item
        if timestamp and item.get("timestamp") == timestamp:
            return item
    return None


def infer_record_mode(record):
    data = record.get("data") or {}
    mode = data.get("mode", "")
    activity = record.get("activity", "")
    if mode:
        return mode
    if "串题" in activity:
        return "theme_linking"
    if "Task 1" in activity:
        return "task1"
    if "Task 2" in activity:
        return "task2"
    if "作文思路" in activity:
        return "ideas"
    if "生成作文题目" in activity:
        return "generate_topic"
    if "参考范文" in activity:
        return "generate_model_answer"
    if "Part 1" in activity:
        return "part1"
    if "Part 2" in activity:
        return "part2"
    if "Part 3" in activity:
        return "part3"
    if "口语反馈" in activity:
        return "speaking_feedback"
    return mode


def replay_record_from_args():
    return find_progress_record(
        session["user_id"],
        request.args.get("replay_id", "").strip(),
        request.args.get("replay_ts", "").strip(),
    )


def result_from_record(record):
    data = record.get("data") or {}
    result_data = data.get("result_data")
    result = data.get("result")
    if result is None and result_data is not None:
        result = json.dumps(result_data, ensure_ascii=False)
    return result, result_data


def speaking_record_replay_payload(record):
    data = record.get("data") or {}
    source_mode = data.get("source_mode") or data.get("part") or ""
    source_data = data.get("source_result_data")
    if isinstance(source_data, str):
        try:
            source_data = json.loads(source_data)
        except (TypeError, ValueError):
            source_data = None
    if isinstance(source_data, dict):
        mode = source_mode if source_mode in {"part1", "part2", "part3"} else infer_record_mode({"data": source_data})
        return mode if mode in {"part1", "part2", "part3"} else "part1", source_data

    question = (data.get("question") or "").strip()
    if not question:
        return "part1", {"questions": [{"question": "Please answer this IELTS speaking question."}]}
    if source_mode == "part2" or "cue card" in question.lower() or "you should say" in question.lower():
        return "part2", {"cue_card": question}
    if source_mode == "part3":
        return "part3", {"discussion_questions": [{"question": question}]}
    return "part1", {"questions": [{"question": question}]}


def form_json_object(name):
    raw = request.form.get(name, "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def speaking_parent_data_from_form():
    parent_data = form_json_object("source_result_data")
    if parent_data is not None:
        return parent_data
    cached_data = session.get("speaking_result_data")
    if cached_data:
        try:
            parsed = json.loads(cached_data)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    return None


def speaking_source_mode_from_form(default_mode):
    source_mode = request.form.get("source_mode", "").strip()
    if source_mode in {"part1", "part2", "part3"}:
        return source_mode
    part = request.form.get("part", "").lower()
    if "1" in part:
        return "part1"
    if "2" in part:
        return "part2"
    if "3" in part:
        return "part3"
    return default_mode


def speaking_part_label(source_mode):
    return {
        "part1": "Part 1",
        "part2": "Part 2",
        "part3": "Part 3",
    }.get(source_mode, "Part 1")


def mark_speaking_focus(parent_data, source_mode):
    if not isinstance(parent_data, dict):
        return parent_data
    if source_mode == "part2":
        parent_data["_focus_feedback"] = "part2"
    else:
        question_index = request.form.get("question_index", "").strip()
        if question_index:
            parent_data["_focus_question_index"] = question_index
    return parent_data


def attach_inline_speaking_result(parent_data, source_mode, action_mode, question, result, action_result_data, extra=None):
    if not isinstance(parent_data, dict):
        return None

    inline = {
        "mode": action_mode,
        "result": result,
        "result_data": action_result_data,
        "user_response": request.form.get("user_response", "").strip(),
        "chinese_answer": request.form.get("chinese_answer", "").strip(),
        "keywords": request.form.get("keywords", "").strip(),
    }
    if isinstance(extra, dict):
        inline.update({key: value for key, value in extra.items() if value not in (None, "")})

    question_key = _normalized_question(question)
    question_index = request.form.get("question_index", "").strip()
    try:
        question_index = int(question_index)
    except (TypeError, ValueError):
        question_index = None
    if source_mode == "part1" and isinstance(parent_data.get("questions"), list):
        questions = parent_data["questions"]
        if question_index is not None and 0 <= question_index < len(questions):
            questions[question_index]["_inline_result"] = inline
        else:
            for item in questions:
                if _normalized_question(item.get("question", "")) == question_key:
                    item["_inline_result"] = inline
                    break
    elif source_mode == "part3" and isinstance(parent_data.get("discussion_questions"), list):
        questions = parent_data["discussion_questions"]
        if question_index is not None and 0 <= question_index < len(questions):
            questions[question_index]["_inline_result"] = inline
        else:
            for item in questions:
                if _normalized_question(item.get("question", "")) == question_key:
                    item["_inline_result"] = inline
                    break
    elif source_mode == "part2":
        parent_data["_inline_result"] = inline
    mark_speaking_focus(parent_data, source_mode)
    return parent_data


def extract_ielts_score(value):
    if value in (None, ""):
        return ""
    if isinstance(value, dict):
        for key in ("overall_score", "score", "band_score", "overall_band"):
            if value.get(key) not in (None, ""):
                return str(value[key])
        return ""
    text = str(value)
    patterns = [
        r"overall_score['\"]?\s*[:：]\s*['\"]?([0-9](?:\.[05])?)",
        r"综合得分\s*[:：]\s*([0-9](?:\.[05])?)",
        r"总体评分\s*[:：]\s*([0-9](?:\.[05])?)",
        r"总分\s*[:：]\s*([0-9](?:\.[05])?)",
        r"score\s*[:：]\s*([0-9](?:\.[05])?)",
        r"([0-9](?:\.[05])?)\s*/\s*9",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def normalize_ielts_score(value):
    if value in (None, ""):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    score = max(0.0, min(9.0, round(score * 2) / 2))
    return score


def normalize_speaking_scores(feedback_data):
    if not isinstance(feedback_data, dict):
        return feedback_data, ""
    breakdown = feedback_data.get("breakdown")
    if not isinstance(breakdown, dict):
        return feedback_data, ""
    scores = []
    for item in breakdown.values():
        if not isinstance(item, dict):
            continue
        score = normalize_ielts_score(item.get("score"))
        if score is not None:
            item["score"] = score
            scores.append(score)
    if scores:
        overall = round((sum(scores) / len(scores)) * 2) / 2
        feedback_data["overall_score"] = overall
    if scores and all(score == 0.0 for score in scores):
        return feedback_data, "模型返回了全 0 分，疑似照抄格式示例，请重新评分。"
    return feedback_data, ""


def calibrate_reference_answer_scores(feedback_data, reference_answer_note):
    if not isinstance(feedback_data, dict) or reference_answer_note == "无":
        return feedback_data
    breakdown = feedback_data.get("breakdown")
    if not isinstance(breakdown, dict):
        return feedback_data
    adjusted = False
    for item in breakdown.values():
        if not isinstance(item, dict):
            continue
        score = normalize_ielts_score(item.get("score"))
        if score is not None and 0 < score < 7.5:
            item["score"] = 7.5
            adjusted = True
    if adjusted:
        scores = [
            normalize_ielts_score(item.get("score"))
            for item in breakdown.values()
            if isinstance(item, dict) and normalize_ielts_score(item.get("score")) is not None
        ]
        if scores:
            feedback_data["overall_score"] = round((sum(scores) / len(scores)) * 2) / 2
    overall = normalize_ielts_score(feedback_data.get("overall_score"))
    if overall is not None and 0 < overall < 7.5:
        feedback_data["overall_score"] = 7.5
    return feedback_data


@lru_cache(maxsize=2)
def get_local_whisper_model(model_name, device, compute_type):
    from faster_whisper import WhisperModel
    return WhisperModel(model_name, device=device, compute_type=compute_type)


def transcribe_audio_file_locally(audio_path):
    if os.getenv("LOCAL_TRANSCRIBE_ENABLED", "true").lower() not in {"1", "true", "yes", "on"}:
        return "", "本地语音转写未启用。"
    if not audio_path or not os.path.exists(audio_path):
        return "", "录音文件不存在，无法本地转写。"
    try:
        from faster_whisper import WhisperModel  # noqa: F401
    except Exception:
        return "", "服务器未安装本地语音识别组件 faster-whisper。"

    model_name = os.getenv("LOCAL_TRANSCRIBE_MODEL", "base")
    device = os.getenv("LOCAL_TRANSCRIBE_DEVICE", "auto")
    compute_type = os.getenv("LOCAL_TRANSCRIBE_COMPUTE_TYPE", "int8")
    try:
        model = get_local_whisper_model(model_name, device, compute_type)
        segments, _ = model.transcribe(
            audio_path,
            language=os.getenv("LOCAL_TRANSCRIBE_LANGUAGE", "en"),
            vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        if not text:
            return "", "本地转写没有识别到文字，请检查录音音量或麦克风权限。"
        return text, ""
    except Exception as e:
        return "", f"本地语音转写失败：{e}"


def transcribe_audio_file_with_api(ai_config, audio_path):
    api_keys = ai_config.get("api_keys", {}) if isinstance(ai_config, dict) else {}
    provider = (ai_config.get("provider", "") if isinstance(ai_config, dict) else "").lower()
    api_key = ""
    base_url = ""

    if api_keys.get("openai"):
        api_key = api_keys["openai"]
        base_url = ""
    elif provider in {"openai", "custom"} and ai_config.get("api_key"):
        api_key = ai_config.get("api_key")
        base_url = ai_config.get("base_url") or ""

    if not api_key:
        return "", "没有可用的语音识别 API。"

    try:
        from openai import OpenAI
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)
        model = os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")
        with open(audio_path, "rb") as audio:
            result = client.audio.transcriptions.create(model=model, file=audio)
        text = getattr(result, "text", "") or ""
        if not text and isinstance(result, dict):
            text = result.get("text", "")
        return text.strip(), ""
    except Exception as e:
        return "", f"语音识别 API 转写失败：{e}"


def transcribe_audio_file(ai_config, audio_path):
    local_text, local_error = transcribe_audio_file_locally(audio_path)
    if local_text:
        return local_text, "", "local"

    api_text, api_error = transcribe_audio_file_with_api(ai_config, audio_path)
    if api_text:
        return api_text, "", "api"

    return "", (
        f"{local_error} {api_error} "
        "如果当前模型不支持语音识别，请先在本地完成语音转文字，再上传文字给模型评分。"
    ).strip(), ""



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
        "local_transcribe_available": local_transcribe_available(),
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
    # 去除代码块包裹
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    # 直接尝试解析
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        pass
    # 尝试从文本中提取 JSON 对象（处理 LLM 在 JSON 前后添加文本的情况）
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace : last_brace + 1])
        except (TypeError, ValueError):
            pass
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
    tracked_profile = refresh_user_level_tracking(user_id)
    date_filter = request.args.get("date", "").strip()
    page = int_query("page", 1)
    all_progress = list(reversed(get_progress(user_id, limit=180)))
    suggestion_record = get_latest_progress_by_activity(user_id, IMPROVEMENT_SUGGESTIONS_ACTIVITY)
    study_plan_record = get_latest_progress_by_activity(user_id, STUDY_PLAN_ACTIVITY)
    suggestions = latest_saved_suggestions([suggestion_record] if suggestion_record else [])
    study_plan = latest_saved_study_plan([study_plan_record] if study_plan_record else [])
    progress = prepare_progress(all_progress)
    if date_filter:
        progress = [p for p in progress if (p.get("timestamp") or "").startswith(date_filter)]
    progress, page, total_pages, total_records = paginate_records(progress, page, 10)
    context = common_context()
    context["profile"] = tracked_profile
    context["level_tracking"] = tracked_profile.get("_tracking", {})
    return render_template(
        "dashboard.html",
        progress=progress,
        page=page,
        total_pages=total_pages,
        total_records=total_records,
        suggestions=suggestions,
        study_plan=study_plan,
        date_filter=date_filter,
        score_options=score_options(),
        target_options=score_options(4.0, 9.0),
        **context,
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
    weak_areas = profile_weak_areas(profile)
    target_score = profile.get("target_score", 6.5)
    current_level = profile.get("current_level", 5.0)
    try:
        raw_suggestions = assistant.generate_improvement_suggestions(
            progress, weak_areas, float(target_score), float(current_level)
        )
    except Exception as exc:
        flash(f"AI 调用失败：{exc}", "error")
        return redirect(url_for("dashboard"))
    suggestions = parse_model_output(raw_suggestions)
    if not isinstance(suggestions, dict):
        suggestions = {"formatted_text": raw_suggestions}
    save_progress(
        user_id,
        IMPROVEMENT_SUGGESTIONS_ACTIVITY,
        {"suggestions": suggestions, "raw": raw_suggestions},
    )
    flash("重点提升建议已生成。", "success")
    return redirect(url_for("dashboard"))


@app.post("/generate-study-plan")
@login_required
def generate_study_plan():
    user_id = session["user_id"]
    profile = load_user_profile(user_id) or default_profile(user_id)
    progress = prepare_progress(list(reversed(get_progress(user_id, limit=100))))
    assistant, _ = current_assistant()
    if assistant is None:
        flash("请先保存可用的 AI API Key。", "error")
        return redirect(url_for("dashboard"))

    current_level, study_weeks, weak_areas = calculate_study_plan_inputs(profile, progress)
    try:
        raw_study_plan = assistant.generate_study_plan(
            current_level=current_level,
            target_score=float(profile.get("target_score", 6.5)),
            weak_areas=weak_areas,
            weeks=study_weeks,
            progress_records=progress,
        )
    except Exception as exc:
        flash(f"AI 调用失败：{exc}", "error")
        return redirect(request.referrer or url_for("dashboard"))
    study_plan = parse_model_output(raw_study_plan)
    if isinstance(study_plan, dict) and "formatted_text" not in study_plan:
        save_progress(user_id, STUDY_PLAN_ACTIVITY, {"plan": study_plan, "raw": raw_study_plan})
    else:
        save_progress(user_id, STUDY_PLAN_ACTIVITY, {"plan_text": raw_study_plan})
    flash("个性化学习计划已生成。", "success")
    return redirect(request.referrer or url_for("dashboard"))


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
    render_result = None
    render_result_data = None
    render_mode = None
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
            source_mode = speaking_source_mode_from_form(mode)
            parent_data = speaking_parent_data_from_form()
            reference_note = reference_answer_note_for_submission(user_response, parent_data, source_mode)
            result = assistant.get_speaking_feedback_direct(
                question,
                user_response,
                target_score,
                speaking_part_label(source_mode),
                reference_note,
            )
            result_data = parse_model_output(result)
            result_data, _score_warning = normalize_speaking_scores(result_data if isinstance(result_data, dict) else None)
            result_data = calibrate_reference_answer_scores(result_data, reference_note)
            score_value = result_data.get("overall_score") if isinstance(result_data, dict) else None
            save_progress(session["user_id"], "口语反馈", {
                "mode": mode,
                "question": question,
                "user_response": user_response,
                "score": score_value,
                "result": result,
                "result_data": result_data,
            })
            refresh_user_level_tracking(session["user_id"])
            parent_with_inline = attach_inline_speaking_result(
                parent_data,
                source_mode,
                mode,
                question,
                result,
                result_data,
                {"score": score_value},
            )
            if parent_with_inline is not None:
                render_result = json.dumps(parent_with_inline, ensure_ascii=False)
                render_result_data = parent_with_inline
                render_mode = source_mode
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
            source_mode = speaking_source_mode_from_form(mode)
            parent_data = speaking_parent_data_from_form()
            parent_with_inline = attach_inline_speaking_result(
                parent_data,
                source_mode,
                mode,
                question,
                result,
                result_data,
            )
            if parent_with_inline is not None:
                render_result = json.dumps(parent_with_inline, ensure_ascii=False)
                render_result_data = parent_with_inline
                render_mode = source_mode
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
            source_mode = speaking_source_mode_from_form(mode)
            parent_data = speaking_parent_data_from_form()
            parent_with_inline = attach_inline_speaking_result(
                parent_data,
                source_mode,
                mode,
                question,
                result,
                None,
            )
            if parent_with_inline is not None:
                render_result = json.dumps(parent_with_inline, ensure_ascii=False)
                render_result_data = parent_with_inline
                render_mode = source_mode
        if result is not None:
            session["speaking_result"] = render_result if render_result is not None else result
            session["speaking_result_data"] = (
                json.dumps(render_result_data, ensure_ascii=False)
                if render_result_data is not None
                else (json.dumps(result_data, ensure_ascii=False) if result_data is not None else None)
            )
            session["speaking_mode"] = render_mode or mode
            if render_result is not None:
                result = render_result
                result_data = render_result_data
                mode = render_mode or mode
    else:
        replay_record = replay_record_from_args()
        if replay_record:
            replay_mode = infer_record_mode(replay_record) or mode
            if replay_mode == "speaking_recording":
                mode, result_data = speaking_record_replay_payload(replay_record)
                result = json.dumps(result_data, ensure_ascii=False)
            else:
                mode = replay_mode
                result, result_data = result_from_record(replay_record)
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
    if isinstance(result_data, dict) and mode in {"part1", "part2", "part3"}:
        result_data = decorate_current_speaking_result(session["user_id"], result_data)
        result = json.dumps(result_data, ensure_ascii=False)
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
        try:
            result = assistant.link_speaking_themes(
                topics,
                request.form.get("main_theme", "个人成长"),
                6.5,
            )
        except Exception as e:
            flash(f"AI 调用失败：{e}", "error")
            result = None
        result_data = parse_model_output(result)
        if result is not None:
            save_progress(session["user_id"], "口语串题方案", {
                "mode": "theme_linking",
                "topics": topics,
                "main_theme": request.form.get("main_theme", "个人成长"),
                "result": result,
                "result_data": result_data,
            })
        if result is not None:
            session["theme_linking_result"] = result
            session["theme_linking_result_data"] = result_data
    else:
        replay_record = replay_record_from_args()
        if replay_record:
            result, result_data = result_from_record(replay_record)
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
    mode = request.form.get("mode") or request.args.get("mode", "task1")
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
            # Store only chart/table fields (not full result_data) to stay within cookie size limit
            session["generated_chart_data"] = json.dumps({
                "chart_type": result_data.get("chart_type", ""),
                "chart_data": result_data.get("chart_data"),
                "table_data": result_data.get("table_data"),
                "chart_image": result_data.get("chart_image", ""),
                "question": result_data.get("question", ""),
                "task_type": task_type,
                "topic_category": result_data.get("topic_category", ""),
                "essay_type": result_data.get("essay_type", ""),
            }, ensure_ascii=False)
            save_progress(session["user_id"], "生成作文题目", {
                "mode": mode,
                "task_type": task_type,
                "result": result,
                "result_data": result_data,
            })
        elif mode == "ideas":
            topic = request.form.get("topic", "").strip()
            question = request.form.get("question", "").strip()
            stored = session.get("generated_chart_data", "")
            topic_data = json.loads(stored) if stored else {}
            chart_data = json.dumps(topic_data.get("chart_data"), ensure_ascii=False) if topic_data.get("chart_data") else ""
            table_data = json.dumps(topic_data.get("table_data"), ensure_ascii=False) if topic_data.get("table_data") else ""
            result = assistant.generate_writing_ideas_with_chart(topic, chart_data, question, table_data)
            result_data = parse_model_output(result)
            session["writing_ideas_topic"] = topic
            session["writing_ideas_question"] = question
            save_progress(session["user_id"], "作文思路互动", {
                "mode": mode,
                "topic": topic,
                "chart_data": chart_data,
                "table_data": table_data,
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
            refresh_user_level_tracking(session["user_id"])
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
            refresh_user_level_tracking(session["user_id"])
        elif mode == "generate_model_answer":
            topic = request.form.get("topic", "").strip()
            task_type = request.form.get("task_type", "Task 2")
            context_raw = request.form.get("topic_context", "").strip()
            if context_raw:
                try:
                    topic_data = json.loads(context_raw)
                except (TypeError, ValueError):
                    topic_data = {}
            else:
                # Retrieve chart/table data from session (generated topic's result_data)
                stored = session.get("generated_chart_data", "")
                topic_data = json.loads(stored) if stored else {}
            topic_data["question"] = topic_data.get("question") or topic
            topic_data["task_type"] = topic_data.get("task_type") or task_type
            chart_type = topic_data.get("chart_type", "")
            chart_data = topic_data.get("chart_data")
            table_data = topic_data.get("table_data")
            result = assistant.generate_model_answer(task_type, topic, chart_type, chart_data, table_data)
            result_data = {
                **topic_data,
                "mode": mode,
                "topic": topic,
                "task_type": task_type,
                "model_answer": result,
            }
            save_progress(session["user_id"], "生成参考范文", {
                "mode": mode,
                "topic": topic,
                "task_type": task_type,
                "chart_type": chart_type,
                "chart_data": chart_data,
                "table_data": table_data,
                "chart_image": topic_data.get("chart_image", ""),
                "question": topic_data.get("question", topic),
                "result": result,
                "result_data": result_data,
            })
        if result is not None:
            session["writing_result"] = result
            session["writing_result_data"] = json.dumps(result_data) if result_data is not None else None
            session["writing_mode"] = mode
    else:
        replay_record = replay_record_from_args()
        if replay_record:
            mode = infer_record_mode(replay_record) or mode
            result, result_data = result_from_record(replay_record)
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
    page = int_query("page", 1)
    all_progress = list(reversed(get_progress(user_id, limit=180)))
    study_plan_record = get_latest_progress_by_activity(user_id, STUDY_PLAN_ACTIVITY)
    study_plan = latest_saved_study_plan([study_plan_record] if study_plan_record else [])
    progress = prepare_progress(all_progress)
    progress, page, total_pages, total_records = paginate_records(progress, page, 10)
    user_words = get_user_words(user_id)
    return render_template(
        "analysis.html",
        progress=progress,
        page=page,
        total_pages=total_pages,
        total_records=total_records,
        study_plan=study_plan,
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
    user_id = session["user_id"]
    audio_file = request.files.get("audio")
    user_text = request.form.get("user_response", "").strip()
    question = request.form.get("question", "口语练习").strip()
    target_score = float_field("target_score", 6.5)
    save_recording = request.form.get("save_recording", "1") == "1"
    source_mode = request.form.get("source_mode", "").strip()
    source_result_data = speaking_parent_data_from_form()

    saved_filename = None
    saved_path = ""

    if audio_file:
        suffix = ".webm"
        filename = audio_file.filename or ""
        if filename.endswith((".m4a", ".mp4")):
            suffix = ".m4a"
        elif filename.endswith(".wav"):
            suffix = ".wav"
        fname = f"{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{suffix}"
        user_dir = os.path.join(os.path.dirname(__file__), "data", "audio", user_id)
        os.makedirs(user_dir, exist_ok=True)
        saved_path = os.path.join(user_dir, fname)
        try:
            audio_file.save(saved_path)
        except Exception as e:
            return jsonify({"error": f"录音保存失败：{e}"}), 500
        saved_filename = f"data/audio/{user_id}/{fname}"

    if not audio_file and not user_text:
        return jsonify({"error": "没有录音数据或文字内容"}), 400

    transcript = user_text
    score_result = ""
    feedback_text = ""
    feedback_data = None
    score_warning = ""
    recorded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 尝试转写和评分
    assistant, ai_config = current_assistant()
    if not isinstance(ai_config, dict):
        ai_config = load_user_ai_config(user_id)

    if not user_text and saved_filename:
        transcript, transcript_error, transcript_source = transcribe_audio_file(ai_config, saved_path)
        if transcript_error:
            feedback_text = f"录音已保存，但{transcript_error}"
    else:
        transcript_source = "text"

    if assistant and (transcript or saved_filename):
        try:
            if transcript and len(transcript) > 10:
                reference_note = reference_answer_note_for_submission(transcript, source_result_data, source_mode)
                feedback = assistant.get_speaking_feedback_direct(
                    question=question,
                    user_response=transcript,
                    target_score=target_score,
                    part=speaking_part_label(source_mode),
                    reference_answer_note=reference_note,
                )
                feedback_text = feedback
                parsed_feedback = parse_model_output(feedback)
                feedback_data = parsed_feedback if isinstance(parsed_feedback, dict) else None
                feedback_data, score_warning = normalize_speaking_scores(feedback_data)
                feedback_data = calibrate_reference_answer_scores(feedback_data, reference_note)
                if score_warning:
                    feedback_text = f"{score_warning}\n\n{feedback_text}"
                normalized_score = feedback_data.get("overall_score") if isinstance(feedback_data, dict) else None
                score_result = normalized_score if normalized_score not in (None, "") else extract_ielts_score(feedback)
                if score_warning:
                    score_result = ""
        except Exception as e:
            feedback_text = f"评分出错：{e}"

    # 保存训练记录
    if save_recording and (saved_filename or (transcript and len(transcript) > 5)):
        save_progress(user_id, "口语录音练习", {
            "question": question,
            "transcript": transcript,
            "user_response": transcript,
            "score": score_result or None,
            "feedback": feedback_text,
            "result": feedback_text,
            "result_data": feedback_data,
            "audio_file": saved_filename or "",
            "recorded_at": recorded_at,
            "transcript_source": transcript_source,
            "source_mode": source_mode,
            "source_result_data": source_result_data,
            "mode": "speaking_recording",
        })
        refresh_user_level_tracking(user_id)

    response_data = {
        "ok": True,
        "transcript": transcript,
        "message": "录音已上传。" if saved_filename else "已提交评分。",
        "transcript_source": transcript_source,
    }
    if feedback_text or saved_filename or transcript:
        response_data["score"] = score_result
        response_data["result_data"] = feedback_data
        inline_payload = {
            "mode": "speaking_recording",
            "result": feedback_text,
            "result_data": feedback_data,
            "user_response": transcript,
            "transcript": transcript,
            "audio_file": saved_filename or "",
            "recorded_at": recorded_at,
            "transcript_source": transcript_source,
            "score": canonical_feedback_score(feedback_data, score_result),
        }
        response_data["inline_feedback_html"] = inline_speaking_feedback_html(inline_payload)
        parent_with_inline = attach_inline_speaking_result(
            source_result_data,
            source_mode,
            "speaking_recording",
            question,
            feedback_text,
            feedback_data,
            inline_payload,
        )
        if parent_with_inline is not None and source_mode in {"part1", "part2", "part3"}:
            response_data["updated_parent"] = True
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
    item = find_progress_record(session["user_id"], record_id, ts)
    if item:
        mode = infer_record_mode(item)
        replay_args = {"replay_id": item.get("id")} if item.get("id") else {"replay_ts": item.get("timestamp", "")}
        if mode in ("part1", "part2", "part3", "speaking_feedback", "keyword_answer", "answer_from_cn", "speaking_recording"):
            replay_args["mode"] = mode
            return redirect(url_for("speaking", **replay_args))
        if mode in ("task1", "task2", "generate_topic", "ideas", "generate_model_answer"):
            replay_args["mode"] = mode
            return redirect(url_for("writing", **replay_args))
        if mode == "theme_linking":
            return redirect(url_for("theme_linking", **replay_args))
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
