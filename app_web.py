import hmac
import html
import hashlib
import json
import math
import os
import random
import re
import uuid
import base64
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from functools import lru_cache, wraps
from importlib.util import find_spec
from urllib.parse import urlsplit, urlunsplit
import ipaddress

from flask import Flask, flash, jsonify, has_request_context, redirect, render_template, request, send_from_directory, session, url_for
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
    save_user_tts_config,
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
    sanitize_speaking_result,
    sanitize_writing_model_answer,
    study_plan_is_placeholder,
    build_personalized_study_plan,
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
        "capabilities": ["文本生成", "写作批改", "口语评分", "TTS"],
    },
    "deepseek": {
        "label": "DeepSeek",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "hint": "OpenAI兼容接口，性价比高",
        "capabilities": ["文本生成", "写作批改", "口语评分"],
    },
    "openai": {
        "label": "OpenAI",
        "model": "gpt-4o-mini",
        "base_url": "",
        "hint": "适合高质量反馈和长文本批改",
        "capabilities": ["文本生成", "写作批改", "口语评分", "语音识别"],
    },
    "siliconflow": {
        "label": "硅基流动",
        "model": "Qwen/Qwen2.5-72B-Instruct",
        "base_url": "https://api.siliconflow.cn/v1",
        "hint": "OpenAI兼容，适合接入多种国产开源模型",
        "capabilities": ["文本生成", "写作批改", "口语评分"],
    },
    "moonshot": {
        "label": "Moonshot Kimi",
        "model": "moonshot-v1-8k",
        "base_url": "https://api.moonshot.cn/v1",
        "hint": "OpenAI兼容，适合长文本理解和中文交互",
        "capabilities": ["文本生成", "写作批改"],
    },
    "zhipu": {
        "label": "智谱 GLM",
        "model": "glm-4-flash",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "hint": "OpenAI兼容，适合中文场景和通用练习",
        "capabilities": ["文本生成", "写作批改"],
    },
    "volcengine": {
        "label": "火山方舟",
        "model": "doubao-1-5-lite-32k-250115",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "hint": "OpenAI兼容，可接入豆包等模型",
        "capabilities": ["文本生成", "写作批改", "语音识别"],
    },
    "xunfei": {
        "label": "讯飞星火",
        "model": "generalv3.5",
        "base_url": "https://spark-api-open.xf-yun.com/v1",
        "hint": "OpenAI兼容配置入口，适合国产模型接入",
        "capabilities": ["文本生成", "语音识别"],
    },
    "mimo": {
        "label": "小米 MiMo",
        "model": "mimo-v2.5-pro",
        "base_url": "https://api.xiaomimimo.com/v1",
        "hint": "OpenAI/Anthropic兼容，支持 MiMo V2.5 系列和 ASR/TTS 能力",
        "capabilities": ["文本生成", "语音识别", "TTS", "多模态"],
    },
    "custom": {
        "label": "OpenAI兼容接口",
        "model": "gpt-4o-mini",
        "base_url": "",
        "hint": "可接入自定义代理或兼容服务",
        "capabilities": ["文本生成", "自定义能力"],
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
    _UTC = _tz.utc
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
        # Server may be in UTC — convert naive UTC to Beijing, otherwise
        # treat as already-Beijing (backward compat with local dev).
        now_utc = _dt.now(_UTC)
        server_is_utc = abs((now_utc.replace(tzinfo=None) - _dt.now()).total_seconds()) < 2
        if server_is_utc:
            dt = dt.replace(tzinfo=_UTC).astimezone(_BJ)
        else:
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


def info_card_grid_html(cards, class_name="feedback-note-grid"):
    rendered = []
    for title, content in cards:
        if content in (None, "", [], {}):
            continue
        body = _html_list(content) if isinstance(content, list) else f"<p>{escape(content)}</p>"
        rendered.append(
            "<article class='feedback-note-card'>"
            f"<strong>{escape(title)}</strong>"
            f"{body}"
            "</article>"
        )
    if not rendered:
        return ""
    return f"<div class='{escape(class_name)}'>{''.join(rendered)}</div>"


def _essay_sentences(text):
    text = str(text or "").strip()
    if not text:
        return []
    chunks = re.split(r"(?<=[.!?。！？])\s+|\n+", text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _diff_tokens_html(left, right):
    token_pattern = r"\s+|[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*|[^\w\s]"
    left_tokens = re.findall(token_pattern, str(left or ""))
    right_tokens = re.findall(token_pattern, str(right or ""))
    matcher = SequenceMatcher(None, left_tokens, right_tokens)
    left_html = []
    right_html = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        left_text = "".join(left_tokens[i1:i2])
        right_text = "".join(right_tokens[j1:j2])
        if tag == "equal":
            left_html.append(escape(left_text))
            right_html.append(escape(right_text))
        elif tag == "delete":
            left_html.append(f"<mark class='diff-del'>{escape(left_text)}</mark>")
        elif tag == "insert":
            right_html.append(f"<mark class='diff-add'>{escape(right_text)}</mark>")
        else:
            if left_text:
                left_html.append(f"<mark class='diff-del'>{escape(left_text)}</mark>")
            if right_text:
                right_html.append(f"<mark class='diff-add'>{escape(right_text)}</mark>")
    return "".join(left_html), "".join(right_html)


def writing_revision_compare_html(original, corrected):
    original_sentences = _essay_sentences(original)
    corrected_sentences = _essay_sentences(corrected)
    if not original_sentences or not corrected_sentences:
        return ""
    matcher = SequenceMatcher(None, original_sentences, corrected_sentences)
    rows = []
    row_index = 1
    empty_added = "<span class='empty-text'>新增句子</span>"
    empty_deleted = "<span class='empty-text'>删除句子</span>"
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        left_group = original_sentences[i1:i2]
        right_group = corrected_sentences[j1:j2]
        pairs = max(len(left_group), len(right_group))
        for offset in range(pairs):
            left = left_group[offset] if offset < len(left_group) else ""
            right = right_group[offset] if offset < len(right_group) else ""
            if tag == "equal":
                left_html = escape(left)
                right_html = escape(right)
            else:
                left_html, right_html = _diff_tokens_html(left, right)
            rows.append(
                "<div class='essay-compare-row'>"
                f"<div class='essay-compare-index'>{row_index}</div>"
                f"<div class='essay-compare-cell original'>{left_html or empty_added}</div>"
                f"<div class='essay-compare-cell revised'>{right_html or empty_deleted}</div>"
                "</div>"
            )
            row_index += 1
    return (
        "<div class='essay-compare'>"
        "<div class='essay-compare-head'><span></span><strong>原文</strong><strong>修正版</strong></div>"
        f"{''.join(rows)}"
        "</div>"
    )


def _chunk_items(items, size):
    return [items[index:index + size] for index in range(0, len(items), size)]


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


def writing_score_encouragement_html(score):
    try:
        score = float(score)
    except (TypeError, ValueError):
        return ""
    if score >= 7.5:
        label, text = "excellent", "太棒了，这篇作文已经有高分范文的质感了！继续保持论证深度和语言准确度。"
    elif score >= 6.5:
        label, text = "good", "真棒，已经站上 6.5+ 的关键台阶了！下一步把观点展开和细节表达再打磨一下。"
    elif score >= 5.5:
        label, text = "steady", "不错，作文框架已经有基础了。接下来重点补强论证、衔接和句式准确性。"
    else:
        label, text = "warm", "别急，这次批改很有价值。先把段落结构和核心观点写清楚，分数会慢慢上来。"
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


def _score_float(value):
    try:
        return max(0.0, min(9.0, float(value)))
    except (TypeError, ValueError):
        return None


def score_visual_html(overall_score, criteria):
    overall = _score_float(overall_score)
    valid_criteria = []
    for label, score in criteria:
        value = _score_float(score)
        if value is not None:
            valid_criteria.append((label, value))
    if overall is None and not valid_criteria:
        return ""
    if overall is None and valid_criteria:
        overall = round(sum(score for _, score in valid_criteria) / len(valid_criteria) * 2) / 2
    percent = int(round((overall / 9) * 100)) if overall is not None else 0
    if overall >= 7.5:
        level = "高分表现"
    elif overall >= 6.5:
        level = "目标达成"
    elif overall >= 5.5:
        level = "稳步提升"
    else:
        level = "基础巩固"
    bars = []
    for label, score in valid_criteria:
        bar_width = int(round((score / 9) * 100))
        bars.append(
            "<div class='score-bar-row'>"
            f"<div class='score-bar-label'>{escape(label)}</div>"
            "<div class='score-bar-track'>"
            f"<span style='width:{bar_width}%'></span>"
            "</div>"
            f"<strong>{score:.1f}</strong>"
            "</div>"
        )
    return (
        "<div class='score-visual'>"
        "<div class='score-ring' style='--score-pct:"
        f"{percent}%;'><div><strong>{overall:.1f}</strong><span>/ 9.0</span></div></div>"
        "<div class='score-visual-main'>"
        f"<p class='eyebrow'>IELTS SCORE</p><h3>{escape(level)}</h3>"
        f"<p>本次表现约达到 {overall:.1f} 分，下面是各评分维度的可视化拆解。</p>"
        f"<div class='score-bars'>{''.join(bars)}</div>"
        "</div></div>"
    )


def speaking_score_visual_html(result_data):
    if not isinstance(result_data, dict):
        return ""
    breakdown = result_data.get("breakdown")
    labels = {
        "fluency_coherence": "流利度与连贯性",
        "lexical_resource": "词汇资源",
        "grammatical_range_accuracy": "语法范围与准确性",
        "pronunciation": "发音",
    }
    criteria = []
    if isinstance(breakdown, dict):
        for key, label in labels.items():
            item = breakdown.get(key)
            if isinstance(item, dict):
                criteria.append((label, item.get("score")))
    return score_visual_html(result_data.get("overall_score"), criteria)


def speaking_feedback_overview_html(result_data):
    if not isinstance(result_data, dict):
        return ""
    breakdown = result_data.get("breakdown")
    if not isinstance(breakdown, dict):
        return ""
    criteria = [
        ("fluency_coherence", "流利度与连贯性"),
        ("lexical_resource", "词汇资源"),
        ("grammatical_range_accuracy", "语法范围与准确性"),
        ("pronunciation", "发音表现"),
    ]
    cards = []
    valid_scores = []
    for key, label in criteria:
        item = breakdown.get(key)
        if not isinstance(item, dict):
            continue
        score = _score_float(item.get("score"))
        if score is not None:
            valid_scores.append(score)
        pct = int(round((score or 0) / 9 * 100))
        details = []
        for field in ["comments", "assessment", "vocabulary_analysis", "grammar_analysis", "pronunciation_analysis"]:
            if item.get(field):
                details.append(f"<p>{escape(item[field])}</p>")
                break
        for field, title in [
            ("strengths", "优点"),
            ("weaknesses", "待改进"),
            ("suggestions", "建议"),
            ("improvement_tips", "提升提示"),
            ("suggested_words", "推荐词汇"),
            ("common_errors", "常见错误"),
        ]:
            if item.get(field):
                details.append(f"<div><strong>{title}</strong>{_html_list(item[field])}</div>")
        score_label = f"{score:.1f}" if score is not None else "--"
        cards.append(
            "<article class='speaking-criterion-card'>"
            "<div class='speaking-criterion-top'>"
            f"<strong>{escape(label)}</strong>"
            f"<span>{score_label}</span>"
            "</div>"
            "<div class='score-bar-track'>"
            f"<span style='width:{pct}%'></span>"
            "</div>"
            f"<div class='speaking-criterion-detail'>{''.join(details)}</div>"
            "</article>"
        )
    overall = _score_float(result_data.get("overall_score"))
    if overall is None and valid_scores:
        overall = round(sum(valid_scores) / len(valid_scores) * 2) / 2
    if overall is None and not cards:
        return ""
    percent = int(round((overall or 0) / 9 * 100))
    overall_label = f"{overall:.1f}" if overall is not None else "--"
    if overall and overall >= 7.5:
        summary = "表达已经很接近高分表现，继续保持展开深度和语言准确度。"
    elif overall and overall >= 6.5:
        summary = "已经达到 6.5+ 的关键区间，下一步重点打磨细节、衔接和自然度。"
    else:
        summary = "本次反馈已按雅思口语四项标准完成，优先补强薄弱维度会更快提分。"
    return (
        "<section class='speaking-feedback-overview'>"
        "<div class='speaking-overview-score'>"
        f"<div class='score-ring' style='--score-pct:{percent}%;'><div><strong>{overall_label}</strong><span>/ 9.0</span></div></div>"
        "<div><p class='eyebrow'>Speaking Score</p><h3>总分与维度概览</h3>"
        f"<p>{escape(summary)}</p></div>"
        "</div>"
        f"<div class='speaking-criteria-grid'>{''.join(cards)}</div>"
        "</section>"
    )


def writing_score_visual_html(result_data):
    if not isinstance(result_data, dict):
        return ""
    labels = {
        "task_achievement": "任务完成度",
        "task_response": "任务回应",
        "coherence_cohesion": "连贯与衔接",
        "lexical_resource": "词汇资源",
        "grammatical_range": "语法多样性与准确性",
        "grammatical_range_accuracy": "语法范围与准确性",
    }
    criteria = []
    for key, label in labels.items():
        item = result_data.get(key)
        if isinstance(item, dict):
            criteria.append((label, item.get("score")))
    return score_visual_html(result_data.get("overall_score"), criteria)


def writing_feedback_overview_html(result_data):
    if not isinstance(result_data, dict):
        return ""
    criteria = [
        ("task_achievement", "任务完成度"),
        ("task_response", "任务回应"),
        ("coherence_cohesion", "连贯与衔接"),
        ("lexical_resource", "词汇资源"),
        ("grammatical_range", "语法多样性与准确性"),
        ("grammatical_range_accuracy", "语法范围与准确性"),
    ]
    cards = []
    valid_scores = []
    for key, label in criteria:
        item = result_data.get(key)
        if not isinstance(item, dict):
            continue
        score = _score_float(item.get("score"))
        if score is not None:
            valid_scores.append(score)
        pct = int(round((score or 0) / 9 * 100))
        details = []
        for field, title in [("comments", "评价"), ("assessment", "评价")]:
            if item.get(field):
                details.append(f"<p>{escape(item[field])}</p>")
                break
        for field, title in [("strengths", "优点"), ("improvements", "建议"), ("suggestions", "建议")]:
            if item.get(field):
                details.append(f"<div><strong>{title}</strong>{_html_list(item[field])}</div>")
        score_label = f"{score:.1f}" if score is not None else "--"
        cards.append(
            "<article class='writing-criterion-card'>"
            "<div class='writing-criterion-top'>"
            f"<strong>{escape(label)}</strong>"
            f"<span>{score_label}</span>"
            "</div>"
            "<div class='score-bar-track'>"
            f"<span style='width:{pct}%'></span>"
            "</div>"
            f"<div class='writing-criterion-detail'>{''.join(details)}</div>"
            "</article>"
        )
    overall = _score_float(result_data.get("overall_score"))
    if overall is None and valid_scores:
        overall = round(sum(valid_scores) / len(valid_scores) * 2) / 2
    if overall is None and not cards:
        return ""
    percent = int(round((overall or 0) / 9 * 100))
    overall_label = f"{overall:.1f}" if overall is not None else "--"
    band_description = result_data.get("band_description") or "本次批改已按雅思写作四项标准完成。"
    return (
        "<section class='writing-feedback-overview'>"
        "<div class='writing-overview-score'>"
        f"<div class='score-ring' style='--score-pct:{percent}%;'><div><strong>{overall_label}</strong><span>/ 9.0</span></div></div>"
        "<div><p class='eyebrow'>Writing Score</p><h3>总分与维度概览</h3>"
        f"<p>{escape(band_description)}</p></div>"
        "</div>"
        f"<div class='writing-criteria-grid'>{''.join(cards)}</div>"
        "</section>"
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
        visual = speaking_feedback_overview_html(data)
        if visual:
            body.append(visual)
        elif data.get("overall_score") is not None:
            body.append(f"<p><strong>AI 评分：</strong>{escape(data['overall_score'])} / 9.0</p>")
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
    writing_criteria = [
        "task_achievement",
        "task_response",
        "coherence_cohesion",
        "lexical_resource",
        "grammatical_range",
        "grammatical_range_accuracy",
    ]
    is_writing_feedback = (
        result_data.get("overall_score") is not None
        and any(isinstance(result_data.get(key), dict) for key in writing_criteria)
    )
    if is_writing_feedback:
        sections.append(writing_feedback_overview_html(result_data))
        essay_content = result_data.get("_essay_content") or result_data.get("essay_content")
        if essay_content:
            sections.append(
                "<details class='result-accordion'><summary>我的作文原文</summary>"
                f"<div class='result-body essay-original'><div>{escape(essay_content)}</div></div></details>"
            )
            revision_compare = writing_revision_compare_html(essay_content, result_data.get("corrected_essay"))
            if revision_compare:
                sections.append(
                    "<details class='result-accordion' open><summary>原文与修正后作文对比</summary>"
                    f"<div class='result-body'>{revision_compare}</div></details>"
                )

    if result_data.get("overall_score") is not None and isinstance(result_data.get("breakdown"), dict):
        sections.append(score_encouragement_html(result_data.get("overall_score")))
        sections.append(speaking_feedback_overview_html(result_data))
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

    if result_data.get("unifying_theme") or result_data.get("unified_story_en") or isinstance(result_data.get("linked_responses"), list):
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

        if result_data.get("cue_card") or result_data.get("unified_story_en"):
            story_body = []
            if result_data.get("story_title"):
                story_body.append(f"<h3>{escape(result_data['story_title'])}</h3>")
            if result_data.get("cue_card"):
                story_body.append(
                    "<details class='result-accordion nested-answer' open><summary>可套用题目卡</summary>"
                    f"<div class='result-body'>{simple_md_filter(result_data.get('cue_card'))}</div></details>"
                )
            if result_data.get("unified_story_cn"):
                story_body.append(f"<p><strong>串题思路：</strong>{escape(result_data['unified_story_cn'])}</p>")
            if result_data.get("unified_story_en"):
                english = str(result_data["unified_story_en"])
                story_body.append(
                    "<p><strong>English Story：</strong><button class='speak-btn' type='button'>朗读故事</button></p>"
                    f"<p class='speak-source theme-story'>{escape(english)}</p>"
                )
            sections.append(
                "<details class='result-accordion' open><summary>统一 Part 2 故事</summary>"
                f"<div class='result-body'>{''.join(story_body)}</div></details>"
            )

        covered_topics = result_data.get("covered_topics") or []
        if isinstance(covered_topics, list) and covered_topics:
            rows = []
            for item in covered_topics:
                if isinstance(item, dict):
                    rows.append(f"<p><strong>{escape(item.get('topic', ''))}：</strong>{escape(item.get('how_it_is_used', ''))}</p>")
                else:
                    rows.append(f"<p>{escape(item)}</p>")
            sections.append(
                "<details class='result-accordion' open><summary>主题融合方式</summary>"
                f"<div class='result-body'>{''.join(rows)}</div></details>"
            )

        if result_data.get("possible_part2_questions"):
            sections.append(
                "<details class='result-accordion'><summary>可迁移 Part 2 题目</summary>"
                f"<div class='result-body'>{_html_list(result_data['possible_part2_questions'])}</div></details>"
            )

        if result_data.get("story_structure") or result_data.get("versatile_phrases"):
            body = []
            if result_data.get("story_structure"):
                body.append("<p><strong>结构：</strong></p>")
                body.append(_html_list(result_data["story_structure"]))
            if result_data.get("versatile_phrases"):
                body.append("<p><strong>表达：</strong></p>")
                body.append(_html_list(result_data["versatile_phrases"]))
            sections.append(
                "<details class='result-accordion'><summary>故事结构与可迁移表达</summary>"
                f"<div class='result-body'>{''.join(body)}</div></details>"
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
                "<details class='result-accordion'><summary><span class='svg-icon icon-analysis' aria-hidden='true'></span> 关键特征</summary>"
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
            f"<div class='result-body'><button class='speak-btn' type='button'>朗读参考答案</button><div class='speak-source'>{simple_md_filter(model_answer)}</div></div></details>"
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
    if not is_writing_feedback:
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
    compact_note_cards = []
    for key, label in list_labels.items():
        value = result_data.get(key)
        if value:
            compact_note_cards.append((label, value))
    notes_html = info_card_grid_html(compact_note_cards)
    if notes_html:
        sections.append(notes_html)

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
        if is_writing_feedback and key in {"overall_score", "band_description"}:
            continue
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

    today = date.today()

    def parse_day(value):
        if not value:
            return None
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        match = re.search(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})", text)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                return None
        return None

    def fmt_day(day):
        return day.strftime("%Y年%m月%d日") if isinstance(day, date) else ""

    def clean_plan_text(value):
        text = html.unescape(str(value or ""))
        text = re.sub(r"</?(?:p|br|div|span|strong|em|ul|ol|li|h[1-6])[^>]*>", " ", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip(" \n\t。")

    def list_value(value):
        if isinstance(value, list):
            return [clean_plan_text(item) for item in value if clean_plan_text(item)]
        if isinstance(value, str) and value.strip():
            cleaned = clean_plan_text(value)
            return [cleaned] if cleaned else []
        return []

    def daily_text(item):
        if not isinstance(item, dict):
            return clean_plan_text(item)
        focus = clean_plan_text(item.get("focus") or item.get("theme") or item.get("title") or "专项训练")
        tasks = list_value(item.get("tasks"))
        review = clean_plan_text(item.get("review") or item.get("goal") or item.get("daily_goal") or "")
        parts = [str(focus)]
        if tasks:
            parts.append("；".join(tasks[:2]))
        if review:
            parts.append(f"复盘：{review}")
        return "。".join(part.strip("。") for part in parts if part)

    def daily_card(item, index):
        if not isinstance(item, dict):
            return ""
        parsed = parse_day(item.get("date"))
        raw_date = fmt_day(parsed) if parsed else str(item.get("date") or f"第 {index} 天")
        date_short = parsed.strftime("%m月%d日") if parsed else raw_date
        focus_text = clean_plan_text(item.get("focus") or item.get("theme") or "专项训练")
        focus = escape(focus_text)
        tasks = list_value(item.get("tasks"))
        type_text = " ".join([focus_text, " ".join(tasks)])
        day_icon = diagnosis_icon(type_text)
        day_type_class = "speaking" if day_icon == "icon-speaking" else "writing" if day_icon == "icon-writing" else "vocab" if day_icon == "icon-vocabulary" else "general"
        task_html = "".join(f"<li>{escape(task)}</li>" for task in tasks[:3])
        if len(tasks) > 3:
            task_html += f"<li class='muted-task'>另有 {len(tasks) - 3} 项细节任务</li>"
        review = clean_plan_text(item.get("review") or item.get("goal") or "")
        review_html = f"<p>{escape(review)}</p>" if review else ""
        return (
            f"<article class='plan-day-card {day_type_class}'>"
            f"<div class='plan-day-date' title='{escape(raw_date)}'><strong>{escape(date_short)}</strong></div>"
            f"<div class='plan-day-main'><h5>{focus}</h5>"
            f"{'<ul>' + task_html + '</ul>' if task_html else ''}"
            f"{review_html}"
            "</div></article>"
        )

    def first_week_goal():
        weekly = plan.get("weekly_schedule")
        if isinstance(weekly, list):
            for item in weekly:
                if not isinstance(item, dict):
                    continue
                goal = item.get("goal") or item.get("weekly_goal")
                focus = item.get("focus") or item.get("theme")
                tasks = list_value(item.get("tasks"))
                if goal:
                    return clean_plan_text(goal)
                if focus:
                    return clean_plan_text(focus)
                if tasks:
                    return tasks[0]
        tips = list_value(plan.get("study_tips"))
        return tips[0] if tips else "完成一次可评分训练，并把反馈转成下一次练习前的检查清单。"

    def diagnosis_icon(skill):
        text = str(skill or "")
        if any(word in text for word in ("口语", "speaking", "Speaking")):
            return "icon-speaking"
        if any(word in text for word in ("写作", "作文", "writing", "Writing")):
            return "icon-writing"
        if any(word in text for word in ("词汇", "单词", "vocabulary", "Vocabulary")):
            return "icon-vocabulary"
        return "icon-analysis"

    daily = plan.get("daily_schedule") if isinstance(plan.get("daily_schedule"), list) else []
    future_daily = []
    for item in daily:
        parsed = parse_day(item.get("date")) if isinstance(item, dict) else None
        if parsed is None or parsed >= today:
            future_daily.append(item)

    today_item = next(
        (item for item in future_daily if isinstance(item, dict) and parse_day(item.get("date")) == today),
        future_daily[0] if future_daily else None,
    )
    parsed_dates = [
        parse_day(item.get("date"))
        for item in future_daily
        if isinstance(item, dict) and parse_day(item.get("date"))
    ]
    exam_day = max(parsed_dates) if parsed_dates else None
    countdown = (exam_day - today).days if exam_day else None
    priority = list_value(plan.get("priority_areas"))
    diagnosis = plan.get("skill_diagnosis") if isinstance(plan.get("skill_diagnosis"), list) else []
    visible_days = future_daily[:6]
    today_plan = daily_text(today_item) if today_item else clean_plan_text(plan.get("overall_assessment") or "今天建议完成一次专项训练，并复盘最近一次 AI 反馈。")
    week_goal = escape(first_week_goal())
    priority_text = escape("、".join(priority[:3]) if priority else "听说读写均衡推进")
    countdown_text = f"{countdown} 天" if isinstance(countdown, int) and countdown >= 0 else "未设置"
    plan_title = escape(plan.get("title") or "个性化学习计划")

    diagnosis_cards = []
    for item in diagnosis[:4]:
        if not isinstance(item, dict):
            continue
        skill = clean_plan_text(item.get("skill") or "能力诊断")
        action = clean_plan_text(item.get("action") or item.get("weakness") or item.get("reason") or "")
        icon_name = diagnosis_icon(skill)
        card_type = "speaking" if icon_name == "icon-speaking" else "writing" if icon_name == "icon-writing" else "vocab" if icon_name == "icon-vocabulary" else "general"
        diagnosis_cards.append(
            f"<article class='plan-diagnosis-card compact {card_type}'>"
            f"<span class='plan-diagnosis-icon'><span class='svg-icon {icon_name}'></span></span>"
            f"<div><strong>{escape(skill)}</strong><p>{escape(action)}</p></div>"
            "</article>"
        )

    day_cards = "".join(daily_card(item, index + 1) for index, item in enumerate(visible_days))
    tips = list_value(plan.get("study_tips"))
    milestones = list_value(plan.get("milestones"))
    note_cards = []
    for label, values in (("学习建议", tips[:2]), ("阶段提醒", milestones[:2])):
        if values:
            note_cards.append(
                "<article class='plan-note-card'>"
                f"<strong>{escape(label)}</strong>{_html_list(values)}"
                "</article>"
            )

    html_output = (
        "<section class='study-plan-dashboard'>"
        "<div class='study-plan-hero'>"
        "<div class='study-plan-copy'>"
        "<span class='plan-kicker'>Personal Plan</span>"
        f"<h4>{plan_title}</h4>"
        f"<p class='today-line'>今天是 {fmt_day(today)}，你的今日学习计划是：<b>{escape(today_plan)}</b></p>"
        "<div class='plan-hero-meta'>"
        f"<span><small>本周目标</small><strong>{week_goal}</strong></span>"
        f"<span><small>考试倒计时</small><strong>{escape(countdown_text)}</strong></span>"
        f"<span><small>重点突破</small><strong>{priority_text}</strong></span>"
        "</div></div>"
        "<div class='study-plan-art' aria-hidden='true'>"
        "<div class='plan-art-tile primary'><span class='plan-art-icon'><span class='svg-icon icon-target'></span></span><div><strong>今日执行</strong><em>训练闭环</em></div></div>"
        "<div class='plan-art-tile speaking'><span class='plan-art-icon'><span class='svg-icon icon-speaking'></span></span><div><strong>口语</strong><em>录音复盘</em></div></div>"
        "<div class='plan-art-tile writing'><span class='plan-art-icon'><span class='svg-icon icon-writing'></span></span><div><strong>写作</strong><em>结构纠错</em></div></div>"
        "</div></div>"
    )
    if day_cards:
        html_output += (
            "<div class='plan-section-head'><div><span>Upcoming</span><h5>未来安排</h5></div>"
            f"<p>已隐藏过期日期，显示接下来 {len(visible_days)} 天。</p></div>"
            f"<div class='plan-days-strip'>{day_cards}</div>"
        )
    if diagnosis_cards or note_cards:
        html_output += "<div class='plan-lower-grid'>"
        if diagnosis_cards:
            html_output += f"<div class='plan-diagnosis-grid compact'>{''.join(diagnosis_cards)}</div>"
        if note_cards:
            html_output += f"<div class='plan-note-grid'>{''.join(note_cards)}</div>"
        html_output += "</div>"
    if not day_cards and not diagnosis_cards and not note_cards:
        html_output += f"<div class='plan-empty'><pre>{escape(json.dumps(plan, ensure_ascii=False, indent=2))}</pre></div>"
    html_output += "</section>"
    return Markup(html_output)


@app.template_filter("simple_list")
def simple_list_filter(items):
    return Markup(_html_list(items if isinstance(items, list) else [items]))


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
        "daily_vocab_goal": 30,
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


def clamp_int(value, default, low, high):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(parsed, high))


def pagination_window(current, total, radius=2):
    if total <= 1:
        return []
    pages = {1, total}
    for value in range(current - radius, current + radius + 1):
        if 1 <= value <= total:
            pages.add(value)
    ordered = sorted(pages)
    result = []
    last = None
    for value in ordered:
        if last is not None and value - last > 1:
            result.append("...")
        result.append(value)
        last = value
    return result



_TYPE_FILTERS = {
    "part1": lambda r: "Part 1" in r.get("display_title", ""),
    "part2": lambda r: "Part 2" in r.get("display_title", ""),
    "part3": lambda r: "Part 3" in r.get("display_title", ""),
    "theme": lambda r: "串题" in r.get("display_title", ""),
    "task1": lambda r: "Task 1" in r.get("display_title", ""),
    "task2": lambda r: "Task 2" in r.get("display_title", ""),
}


def _matches_type_filter(record, type_filter):
    fn = _TYPE_FILTERS.get(type_filter)
    return fn(record) if fn else True

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
    config["effective_model"] = assistant.model
    config["requested_model"] = assistant.requested_model
    config["used_model_fallback"] = assistant.used_model_fallback
    return assistant, config


def local_transcribe_available():
    return find_spec("faster_whisper") is not None


def provider_status_for(ai_config):
    api_keys = ai_config.get("api_keys", {})
    return {key: bool(api_keys.get(key)) for key in AI_PROVIDERS}


def _provider_client_params(provider, api_key, base_url=""):
    defaults = AI_PROVIDERS.get(provider, AI_PROVIDERS["custom"])
    resolved_base_url = base_url or defaults.get("base_url", "")
    if provider == "tongyi":
        resolved_base_url = resolved_base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    return {"api_key": api_key, "base_url": resolved_base_url or None}


def fetch_provider_models(provider, api_key, base_url=""):
    if not api_key:
        return [], "请先填写 API Key。"
    try:
        from openai import OpenAI
        params = _provider_client_params(provider, api_key, base_url)
        client_kwargs = {"api_key": params["api_key"]}
        if params.get("base_url"):
            client_kwargs["base_url"] = params["base_url"]
        client = OpenAI(**client_kwargs)
        models = client.models.list()
        items = []
        for item in getattr(models, "data", []) or []:
            model_id = getattr(item, "id", "") or (item.get("id") if isinstance(item, dict) else "")
            if model_id:
                items.append(model_id)
        return sorted(set(items))[:200], ""
    except Exception as exc:
        return [], str(exc)


def classify_model_usage(model_name):
    name = (model_name or "").lower()
    if any(token in name for token in ["tts", "speech", "voice", "audio-speech"]):
        return {"kind": "tts", "label": "适合朗读 / TTS", "recommended_for": "tts"}
    if any(token in name for token in ["asr", "whisper", "transcribe", "stt", "audio-transcription"]):
        return {"kind": "asr", "label": "适合语音识别 / ASR", "recommended_for": "asr"}
    if "ocr" in name:
        return {"kind": "ocr", "label": "适合 OCR 识别", "recommended_for": "other"}
    if any(token in name for token in ["embedding", "embed", "rerank", "moderation"]):
        return {"kind": "other", "label": "工具模型，不适合生成", "recommended_for": "other"}
    if any(token in name for token in ["vision", "vl", "omni", "4o", "chat", "instruct", "qwen", "deepseek", "glm", "moonshot", "mimo", "doubao", "spark"]):
        return {"kind": "text", "label": "适合生成题目 / 批改", "recommended_for": "text"}
    return {"kind": "text", "label": "可能适合文本生成", "recommended_for": "text"}


def describe_models(models):
    return [
        {"id": model, **classify_model_usage(model)}
        for model in models
    ]


def default_tts_voices(provider):
    if provider == "openai":
        return ["marin", "cedar", "coral", "alloy", "ash", "ballad", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse"]
    if provider == "mimo":
        return ["Chloe", "Mia", "Milo", "Dean", "mimo_default", "冰糖", "茉莉", "苏打", "白桦"]
    if provider == "tongyi":
        return ["Cherry", "Serena", "Ethan", "Chelsie"]
    return ["default", "alloy", "male", "female"]


def tts_voice_candidates(provider, configured_voice):
    voices = []
    if configured_voice:
        voices.append(configured_voice)
    voices.extend(default_tts_voices(provider))
    if provider == "openai":
        voices.extend(["coral", "alloy"])
    elif provider == "mimo":
        voices.extend(["Chloe", "Mia", "mimo_default"])
    else:
        voices.extend(["default", "alloy"])
    return list(dict.fromkeys([voice.strip() for voice in voices if voice and voice.strip()]))


def synthesize_tts_audio(provider, api_key, model, base_url, voice, text):
    provider = (provider or "").lower()
    model = model or ("mimo-v2.5-tts" if provider == "mimo" else "gpt-4o-mini-tts")
    base_url = base_url or AI_PROVIDERS.get(provider, {}).get("base_url", "")
    attempted = []
    last_error = None
    from openai import OpenAI

    if provider == "mimo":
        client = OpenAI(api_key=api_key, base_url=base_url or "https://api.xiaomimimo.com/v1")
        instruction = "Natural IELTS examiner voice. Clear pronunciation, steady pace, warm and professional tone."
        for candidate_voice in tts_voice_candidates(provider, voice or "Chloe"):
            attempted.append(candidate_voice)
            try:
                completion = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "user", "content": instruction},
                        {"role": "assistant", "content": text},
                    ],
                    audio={"format": "wav", "voice": candidate_voice},
                )
                message = completion.choices[0].message
                audio = getattr(message, "audio", None)
                audio_data = None
                if isinstance(audio, dict):
                    audio_data = audio.get("data")
                elif audio is not None:
                    audio_data = getattr(audio, "data", None)
                if not audio_data:
                    raise RuntimeError("接口未返回 message.audio.data")
                return base64.b64decode(audio_data), "audio/wav", candidate_voice, attempted
            except Exception as exc:
                last_error = exc
                continue
        raise RuntimeError(f"MiMo TTS 调用失败：{last_error}")

    if provider != "openai":
        label = AI_PROVIDERS.get(provider, {}).get("label", provider or "未知供应商")
        raise RuntimeError(f"{label} 的 TTS 不是 OpenAI /v1/audio/speech 兼容接口，当前版本未启用。建议使用 OpenAI 或小米 MiMo 并先测试通过。")

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)
    for candidate_voice in tts_voice_candidates(provider, voice or "coral"):
        attempted.append(candidate_voice)
        try:
            response = client.audio.speech.create(
                model=model,
                voice=candidate_voice,
                input=text,
                instructions="Speak like a calm IELTS examiner. Clear, natural, and easy to follow.",
                response_format="mp3",
            )
            audio_bytes = response.read() if hasattr(response, "read") else bytes(response)
            if not audio_bytes:
                raise RuntimeError("接口未返回音频内容")
            return audio_bytes, "audio/mpeg", candidate_voice, attempted
        except TypeError:
            try:
                response = client.audio.speech.create(
                    model=model,
                    voice=candidate_voice,
                    input=text,
                    response_format="mp3",
                )
                audio_bytes = response.read() if hasattr(response, "read") else bytes(response)
                if not audio_bytes:
                    raise RuntimeError("接口未返回音频内容")
                return audio_bytes, "audio/mpeg", candidate_voice, attempted
            except Exception as exc:
                last_error = exc
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"OpenAI TTS 调用失败：{last_error}")


def test_provider_connection(provider, api_key, model, base_url=""):
    if not api_key:
        return False, "请先填写 API Key。"
    try:
        assistant = TongyiIELTSAssistant(
            api_key,
            provider=provider,
            model=model or AI_PROVIDERS.get(provider, AI_PROVIDERS["custom"]).get("model", ""),
            base_url=base_url or AI_PROVIDERS.get(provider, {}).get("base_url", ""),
        )
        response = assistant.llm.invoke("Reply with OK only.")
        text = getattr(response, "content", str(response))
        return True, f"连接成功：{text[:80]}"
    except Exception as exc:
        return False, f"连接失败：{exc}"


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
    # 活动名为“口语反馈” 或 模式为 speaking_feedback 或 存有完整 feedback 数据
    return (
        record.get("activity") == "口语反馈"
        or (isinstance(data, dict) and data.get("mode") == "speaking_feedback")
        or (isinstance(data, dict) and isinstance(data.get("result_data"), dict)
            and data["result_data"].get("overall_score") not in (None, "")
            and data["result_data"].get("breakdown"))
    )


def is_attachable_speaking_feedback(record):
    data = record.get("data") if isinstance(record, dict) else {}
    return (
        is_speaking_feedback_record(record)
        or (
            isinstance(data, dict)
            and data.get("mode") == "speaking_recording"
            and data.get("result_data")
        )
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
        source_label = {"local": "本地转写", "api": "音频转写", "text": "文本提交"}.get(
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
    # Prefer the most recent "口语反馈" over "口语录音练习"
    best = None
    best_ts = ""
    for fb in feedbacks:
        is_feedback = (fb.get("mode") or "") in ("speaking_feedback", "口语反馈")
        ts = fb.get("timestamp") or fb.get("recorded_at") or ""
        if not best or is_feedback or ts > best_ts:
            best = fb
            best_ts = ts
    if not best:
        return None
    result_data = best.get("result_data")
    latest_score = (
        result_data.get("overall_score")
        if isinstance(result_data, dict) and result_data.get("overall_score") not in (None, "")
        else best.get("score")
    )
    return {
        "mode": best.get("mode") or "speaking_feedback",
        "result": best.get("result", ""),
        "result_data": best.get("result_data"),
        "user_response": best.get("user_response", "") or best.get("transcript", ""),
        "transcript": best.get("transcript", ""),
        "audio_file": best.get("audio_file", ""),
        "recorded_at": best.get("recorded_at") or best.get("timestamp", ""),
        "transcript_source": best.get("transcript_source", ""),
        "score": latest_score,
        "chinese_answer": "",
        "keywords": "",
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
        and not is_inline_generation_record(record)
    ]


INLINE_GENERATION_ACTIVITIES = {
    "生成参考范文",
    "关键词生成答案",
    "中文思路生成英文口语答案",
}


def is_inline_generation_record(record):
    return record.get("activity") in INLINE_GENERATION_ACTIVITIES


def _record_lookup_key(record):
    data = record.get("data") if isinstance(record, dict) else {}
    data = data if isinstance(data, dict) else {}
    result_data = data.get("result_data")
    candidates = [
        data.get("question"),
        data.get("topic"),
        data.get("original_question"),
        data.get("source_question"),
    ]
    if isinstance(result_data, dict):
        candidates.extend([
            result_data.get("question"),
            result_data.get("topic"),
            result_data.get("cue_card"),
        ])
    for candidate in candidates:
        key = _normalized_question(str(candidate or ""))
        if key:
            return key
    return ""


def _record_display_meta(record):
    activity = record.get("activity", "")
    data = record.get("data") if isinstance(record, dict) else {}
    data = data if isinstance(data, dict) else {}
    mode = data.get("mode", "")
    source_mode = data.get("source_mode", "")
    task_type = data.get("task_type", "")

    if "Part 1" in activity or mode == "part1" or source_mode == "part1":
        return {"icon": "speaking", "title": "口语 Part 1 训练", "badge": "Speaking"}
    if "Part 2" in activity or mode == "part2" or source_mode == "part2":
        return {"icon": "target", "title": "口语 Part 2 训练", "badge": "Cue Card"}
    if "Part 3" in activity or mode == "part3" or source_mode == "part3":
        return {"icon": "brain", "title": "口语 Part 3 训练", "badge": "Discussion"}
    if "口语串题" in activity:
        return {"icon": "theme", "title": "口语串题训练", "badge": "Theme"}
    if "Task 1" in activity or task_type == "Task 1" or mode == "task1":
        return {"icon": "chart", "title": "写作 Task 1 训练", "badge": "Writing"}
    if "Task 2" in activity or task_type == "Task 2" or mode == "task2":
        return {"icon": "writing", "title": "写作 Task 2 训练", "badge": "Writing"}
    if "口语" in activity or mode in {"speaking_feedback", "speaking_recording"}:
        return {"icon": "mic", "title": "口语训练", "badge": "Speaking"}
    if "作文" in activity or "写作" in activity:
        return {"icon": "writing", "title": "写作训练", "badge": "Writing"}
    if "背单词" in activity or "词" in activity:
        return {"icon": "vocabulary", "title": "背单词训练", "badge": "Vocabulary"}
    return {"icon": "practice", "title": "学习训练", "badge": "Practice"}


def _result_question_count(result_data):
    if not isinstance(result_data, dict):
        return 0
    if isinstance(result_data.get("questions"), list):
        return len(result_data["questions"])
    if isinstance(result_data.get("discussion_questions"), list):
        return len(result_data["discussion_questions"])
    if result_data.get("cue_card"):
        return 1
    if result_data.get("question"):
        return 1
    return 0


def _feedback_score_values(feedbacks):
    scores = []
    for feedback in feedbacks or []:
        result_data = feedback.get("result_data")
        raw_score = (
            result_data.get("overall_score")
            if isinstance(result_data, dict)
            else feedback.get("score")
        )
        score = normalize_ielts_score(raw_score)
        if score is not None:
            scores.append(score)
    return scores


def _record_progress_summary(record):
    data = record.get("data") if isinstance(record, dict) else {}
    data = data if isinstance(data, dict) else {}
    result_data = data.get("result_data")
    generated = _result_question_count(result_data)
    practiced = 0
    scores = []

    if isinstance(result_data, dict):
        if isinstance(result_data.get("questions"), list):
            for item in result_data["questions"]:
                if isinstance(item, dict) and item.get("_feedbacks"):
                    practiced += 1
                    scores.extend(_feedback_score_values(item.get("_feedbacks")))
        if isinstance(result_data.get("discussion_questions"), list):
            for item in result_data["discussion_questions"]:
                if isinstance(item, dict) and item.get("_feedbacks"):
                    practiced += 1
                    scores.extend(_feedback_score_values(item.get("_feedbacks")))
        if result_data.get("_feedbacks"):
            practiced += 1
            scores.extend(_feedback_score_values(result_data.get("_feedbacks")))

    own_score = score_from_progress_record(record)
    if own_score is not None:
        scores.append(own_score)
        practiced = max(practiced, 1)
        generated = max(generated, 1)
    if data.get("user_response") or data.get("essay_content") or data.get("transcript"):
        practiced = max(practiced, 1)
        generated = max(generated, 1)
    if not generated and (data.get("question") or data.get("topic")):
        generated = 1

    score = round_ielts_band(sum(scores) / len(scores)) if scores else None
    practiced = min(practiced, generated) if generated else practiced
    percent = int((practiced / generated) * 100) if generated else (100 if practiced else 0)
    return {
        "generated": generated,
        "practiced": practiced,
        "score": score,
        "best_score": score,
        "percent": max(0, min(100, percent)),
        "question_label": f"{practiced}/{generated}" if generated else "0/0",
    }


def decorate_progress_display(records):
    main_records = visible_progress(records)
    main_by_key = {}
    for record in main_records:
        meta = _record_display_meta(record)
        record.update({
            "display_icon": meta["icon"],
            "display_title": meta["title"],
            "display_badge": meta["badge"],
        })
        data = record.get("data")
        if isinstance(data, dict):
            data.setdefault("_related_records", [])
        key = _record_lookup_key(record)
        if key:
            main_by_key.setdefault(key, record)

    for record in records:
        if not is_inline_generation_record(record):
            continue
        key = _record_lookup_key(record)
        parent = main_by_key.get(key)
        if not parent:
            continue
        parent_data = parent.get("data")
        if isinstance(parent_data, dict):
            parent_data.setdefault("_related_records", []).append(record)

    for record in main_records:
        record["progress_summary"] = _record_progress_summary(record)

    return main_records


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
    return with_display_scores(decorate_progress_display(attach_speaking_feedback(records)))


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
    if isinstance(plan, dict) and not study_plan_is_placeholder(plan):
        return plan
    text_plan = data.get("plan_text") or data.get("result") or ""
    return "" if study_plan_is_placeholder(text_plan) else text_plan


def progress_timestamp(record):
    if not isinstance(record, dict):
        return ""
    return record.get("timestamp") or ""


def is_guidance_activity(activity):
    return activity in {IMPROVEMENT_SUGGESTIONS_ACTIVITY, STUDY_PLAN_ACTIVITY}


def is_training_record_for_guidance(record):
    if not isinstance(record, dict) or is_guidance_activity(record.get("activity", "")):
        return False
    score = score_from_progress_record(record)
    if score is not None:
        return True
    data = record.get("data", {})
    if not isinstance(data, dict):
        return False
    mode = data.get("mode", "")
    activity = record.get("activity", "")
    return mode in {"speaking_feedback", "speaking_recording", "task1", "task2"} or "批改" in activity or "反馈" in activity


def latest_training_record(records):
    candidates = [record for record in records if is_training_record_for_guidance(record)]
    if not candidates:
        return None
    return max(candidates, key=progress_timestamp)


def guidance_needs_refresh(records, activity):
    latest_training = latest_training_record(records)
    if not latest_training:
        return False
    latest_guidance = latest_activity_record(records, activity)
    if not latest_guidance:
        return True
    return progress_timestamp(latest_training) > progress_timestamp(latest_guidance)


def save_ai_suggestions(user_id, profile, progress, silent=False):
    assistant, _ = current_assistant()
    if assistant is None:
        if not silent:
            flash("请先保存可用的 AI API Key。", "error")
        return None
    weak_areas = profile_weak_areas(profile)
    target_score = round_ielts_band(profile.get("target_score", 6.5))
    current_level = round_ielts_band(profile.get("current_level", 5.0))
    raw_suggestions = assistant.generate_improvement_suggestions(
        progress,
        weak_areas,
        target_score,
        current_level,
    )
    suggestions = parse_model_output(raw_suggestions)
    if not isinstance(suggestions, dict):
        suggestions = {"formatted_text": raw_suggestions}
    save_progress(
        user_id,
        IMPROVEMENT_SUGGESTIONS_ACTIVITY,
        {"suggestions": suggestions, "raw": raw_suggestions},
    )
    return suggestions


def save_ai_study_plan(user_id, profile, progress, silent=False):
    assistant, _ = current_assistant()
    current_level, study_weeks, weak_areas = calculate_study_plan_inputs(profile, progress)
    target_score = round_ielts_band(profile.get("target_score", 6.5))
    exam_date = profile.get("exam_date") or ""
    countdown = exam_countdown(profile)
    days_until_exam = countdown.get("days") if countdown else None
    raw_study_plan = ""
    if assistant is not None:
        raw_study_plan = assistant.generate_study_plan(
            current_level=round_ielts_band(current_level),
            target_score=target_score,
            weak_areas=weak_areas,
            weeks=study_weeks,
            progress_records=progress,
            exam_date=exam_date,
            days_until_exam=days_until_exam,
        )
        study_plan = parse_model_output(raw_study_plan)
    else:
        if not silent:
            flash("请先保存可用的 AI API Key。", "error")
        study_plan = None

    fallback_plan = build_personalized_study_plan(
        current_level=round_ielts_band(current_level),
        target_score=target_score,
        weak_areas=weak_areas,
        weeks=study_weeks,
        history_count=len([r for r in progress if is_training_record_for_guidance(r)]),
        exam_date=exam_date,
    )
    if not isinstance(study_plan, dict) or "formatted_text" in study_plan or study_plan_is_placeholder(study_plan):
        study_plan = fallback_plan
    else:
        if exam_date and not study_plan.get("daily_schedule"):
            study_plan["daily_schedule"] = fallback_plan.get("daily_schedule", [])
        if not study_plan.get("skill_diagnosis"):
            study_plan["skill_diagnosis"] = fallback_plan.get("skill_diagnosis", [])
    save_progress(user_id, STUDY_PLAN_ACTIVITY, {"plan": study_plan, "raw": raw_study_plan})
    return study_plan


def maybe_auto_refresh_learning_guidance(user_id, profile, progress):
    refreshed = {"suggestions": False, "study_plan": False, "skipped": False}
    latest_training = latest_training_record(progress)
    if not latest_training:
        return refreshed
    latest_training_ts = progress_timestamp(latest_training)
    session_key = f"auto_guidance_refreshed_ts_{user_id}"
    if session.get(session_key) == latest_training_ts:
        return refreshed
    needs_suggestions = guidance_needs_refresh(progress, IMPROVEMENT_SUGGESTIONS_ACTIVITY)
    needs_plan = guidance_needs_refresh(progress, STUDY_PLAN_ACTIVITY)
    if not (needs_suggestions or needs_plan):
        session[session_key] = latest_training_ts
        return refreshed

    prepared = prepare_progress(progress)
    try:
        if needs_suggestions:
            refreshed["suggestions"] = save_ai_suggestions(user_id, profile, prepared, silent=True) is not None
        if needs_plan:
            refreshed["study_plan"] = save_ai_study_plan(user_id, profile, prepared, silent=True) is not None
    except Exception as exc:
        print(f"自动更新学习方案失败: {exc}")
        refreshed["skipped"] = True
    session[session_key] = latest_training_ts
    return refreshed


DIMENSION_LABELS = {
    "fluency_coherence": "口语流利度",
    "speaking_lexical_resource": "口语词汇",
    "speaking_grammatical_range_accuracy": "口语语法",
    "pronunciation": "发音表现",
    "task_achievement": "任务完成",
    "task_response": "任务回应",
    "coherence_cohesion": "连贯衔接",
    "writing_lexical_resource": "写作词汇",
    "writing_grammatical_range_accuracy": "写作语法",
}


def guidance_dimension_overview(records, profile):
    target = round_ielts_band(profile_band(profile, "target_score", 6.5))
    buckets = {}
    for record in records:
        if not is_training_record_for_guidance(record):
            continue
        data = record.get("data", {}) if isinstance(record, dict) else {}
        result_data = data.get("result_data", {}) if isinstance(data, dict) else {}
        if not isinstance(result_data, dict):
            continue
        record_skill = progress_skill(record)
        breakdown = result_data.get("breakdown")
        if isinstance(breakdown, dict):
            for key, value in breakdown.items():
                if isinstance(value, dict) and value.get("score") not in (None, ""):
                    bucket_key = f"{record_skill}_{key}" if key in {"lexical_resource", "grammatical_range_accuracy"} and record_skill else key
                    try:
                        buckets.setdefault(bucket_key, []).append(float(value.get("score")))
                    except (TypeError, ValueError):
                        continue
        for key in [
            "task_achievement",
            "task_response",
            "coherence_cohesion",
            "lexical_resource",
            "grammatical_range_accuracy",
        ]:
            value = result_data.get(key)
            if isinstance(value, dict) and value.get("score") not in (None, ""):
                bucket_key = f"{record_skill}_{key}" if key in {"lexical_resource", "grammatical_range_accuracy"} and record_skill else key
                try:
                    buckets.setdefault(bucket_key, []).append(float(value.get("score")))
                except (TypeError, ValueError):
                    continue

    dimensions = []
    for key, scores in buckets.items():
        if not scores:
            continue
        score = round_ielts_band(sum(scores[-5:]) / len(scores[-5:]))
        dimensions.append({
            "key": key,
            "label": DIMENSION_LABELS.get(key, key.replace("_", " ")),
            "score": score,
            "count": len(scores),
            "gap": round_ielts_band(max(0.0, target - score)),
            "percent": max(0, min(100, int((score / max(target, 0.5)) * 100))),
            "type": "speaking" if key.startswith("speaking_") or key in {"fluency_coherence", "pronunciation"} else "writing" if key.startswith("writing_") or key in {"task_achievement", "task_response", "coherence_cohesion"} else "shared",
        })
    dimensions.sort(key=lambda item: (-item["gap"], item["score"]))
    return dimensions[:8]


def learning_guidance_overview(profile, records, suggestions=None, study_plan=None):
    target = round_ielts_band(profile_band(profile, "target_score", 6.5))
    skill_items = skill_score_overview(profile)
    weak_items = sorted(skill_items, key=lambda item: item["gap"], reverse=True)
    training_records = [record for record in records if is_training_record_for_guidance(record)]
    scored_records = [record for record in training_records if score_from_progress_record(record) is not None]
    latest_scored = max(scored_records, key=progress_timestamp) if scored_records else None
    latest_score = score_from_progress_record(latest_scored) if latest_scored else None
    best_score = max((score_from_progress_record(record) or 0 for record in scored_records), default=None)
    latest_record = latest_training_record(records)
    latest_guidance = latest_activity_record(records, STUDY_PLAN_ACTIVITY) or latest_activity_record(records, IMPROVEMENT_SUGGESTIONS_ACTIVITY)
    return {
        "target": target,
        "weakest": weak_items[:2],
        "training_count": len(training_records),
        "scored_count": len(scored_records),
        "latest_score": round_ielts_band(latest_score) if latest_score is not None else None,
        "best_score": round_ielts_band(best_score) if best_score is not None else None,
        "latest_training_date": (progress_timestamp(latest_record)[:10] if latest_record else ""),
        "latest_guidance_date": (progress_timestamp(latest_guidance)[:10] if latest_guidance else ""),
        "has_suggestions": bool(suggestions),
        "has_study_plan": bool(study_plan),
        "dimensions": guidance_dimension_overview(records, profile),
    }


def ensure_exam_daily_schedule(profile, study_plan, progress):
    exam_date = profile.get("exam_date") or ""
    if not exam_date or not isinstance(study_plan, dict) or study_plan.get("daily_schedule"):
        return study_plan
    current_level, study_weeks, weak_areas = calculate_study_plan_inputs(profile, progress)
    fallback_plan = build_personalized_study_plan(
        current_level=round_ielts_band(current_level),
        target_score=round_ielts_band(profile.get("target_score", 6.5)),
        weak_areas=weak_areas,
        weeks=study_weeks,
        history_count=len([r for r in progress if is_training_record_for_guidance(r)]),
        exam_date=exam_date,
    )
    merged = dict(study_plan)
    merged["daily_schedule"] = fallback_plan.get("daily_schedule", [])
    if not merged.get("skill_diagnosis"):
        merged["skill_diagnosis"] = fallback_plan.get("skill_diagnosis", [])
    return merged


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


def skill_score_overview(profile):
    target = profile_band(profile, "target_score", 6.5)
    items = [
        ("听力", "listening", "listening_level"),
        ("口语", "speaking", "speaking_level"),
        ("阅读", "reading", "reading_level"),
        ("写作", "writing", "writing_level"),
    ]
    overview = []
    for label, icon, key in items:
        score = round_ielts_band(profile_band(profile, key, 5.0))
        completion = 100 if target <= 0 else int((score / target) * 100)
        overview.append({
            "label": label,
            "icon": icon,
            "score": score,
            "target": target,
            "percent": max(0, min(100, completion)),
            "target_percent": 100,
            "gap": round_ielts_band(max(0.0, target - score)),
        })
    return overview


def dashboard_goal_progress(records, weekly_target=5):
    now = datetime.now()
    week_start = now.date().toordinal() - now.weekday()
    practiced = 0
    for record in records:
        ts = record.get("timestamp") or ""
        try:
            date_value = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
        except (TypeError, ValueError):
            continue
        if date_value.toordinal() < week_start:
            continue
        summary = record.get("progress_summary") or _record_progress_summary(record)
        practiced += max(1, int(summary.get("practiced") or 0)) if summary.get("practiced") else 0
    target = max(1, int(weekly_target or 5))
    return {
        "done": practiced,
        "target": target,
        "percent": min(100, int((practiced / target) * 100)),
    }


def exam_countdown(profile):
    exam_date = profile.get("exam_date") or ""
    try:
        days = (datetime.strptime(exam_date, "%Y-%m-%d").date() - datetime.now().date()).days
    except (TypeError, ValueError):
        return None
    return {"days": max(0, days), "date": exam_date}


def ability_trend_data(records, profile, limit=7):
    points = []
    for record in records:
        skill = progress_skill(record)
        if skill not in {"speaking", "writing"}:
            continue
        score = score_from_progress_record(record)
        if score is None:
            continue
        points.append({
            "date": (record.get("timestamp") or "")[:10],
            "label": "口语" if skill == "speaking" else "写作",
            "skill": skill,
            "score": score,
            "percent": max(0, min(100, int((score / 9.0) * 100))),
        })
    points = points[-limit:]
    if not points:
        points = [
            {"date": "当前", "label": "口语", "skill": "speaking", "score": profile_band(profile, "speaking_level"), "percent": int(profile_band(profile, "speaking_level") / 9 * 100)},
            {"date": "当前", "label": "写作", "skill": "writing", "score": profile_band(profile, "writing_level"), "percent": int(profile_band(profile, "writing_level") / 9 * 100)},
        ]
    return points


def ability_trend_chart(records, profile, limit=6):
    dates = []
    for record in records:
        date = (record.get("timestamp") or "")[:10]
        if date and date not in dates:
            dates.append(date)
    if not dates:
        dates = [datetime.now().strftime("%Y-%m-%d")]
    dates = dates[-limit:]

    base_scores = {
        "listening": profile_band(profile, "listening_level"),
        "speaking": profile_band(profile, "speaking_level"),
        "reading": profile_band(profile, "reading_level"),
        "writing": profile_band(profile, "writing_level"),
    }
    daily_scores = {date: {key: [] for key in base_scores} for date in dates}
    for record in records:
        date = (record.get("timestamp") or "")[:10]
        if date not in daily_scores:
            continue
        skill = progress_skill(record)
        if skill not in daily_scores[date]:
            continue
        score = score_from_progress_record(record)
        if score is not None:
            daily_scores[date][skill].append(score)

    current = dict(base_scores)
    chart_dates = []
    for date in dates:
        day = {"date": date, "short": date[5:] if len(date) >= 10 else date}
        for skill in base_scores:
            scores = daily_scores[date][skill]
            if scores:
                current[skill] = round_ielts_band(sum(scores) / len(scores))
            day[skill] = current[skill]
        chart_dates.append(day)

    width, height = 620, 260
    left, right, top, bottom = 42, 18, 22, 34
    usable_w = width - left - right
    usable_h = height - top - bottom

    def point_for(index, score):
        x = left + (usable_w * index / max(1, len(chart_dates) - 1))
        y = top + usable_h - (max(0, min(9, score)) / 9.0) * usable_h
        return f"{x:.1f},{y:.1f}"

    def dot_for(index, score):
        x = left + (usable_w * index / max(1, len(chart_dates) - 1))
        y = top + usable_h - (max(0, min(9, score)) / 9.0) * usable_h
        return {"x": x, "y": y, "score": score}

    series_meta = [
        ("listening", "听力", "#2f8df7"),
        ("speaking", "口语", "#19ad83"),
        ("reading", "阅读", "#8265e8"),
        ("writing", "写作", "#ff922e"),
    ]
    series = []
    for key, label, color in series_meta:
        values = [day[key] for day in chart_dates]
        series.append({
            "key": key,
            "label": label,
            "color": color,
            "latest": values[-1] if values else base_scores[key],
            "points": " ".join(point_for(i, score) for i, score in enumerate(values)),
            "dots": [dot_for(i, score) for i, score in enumerate(values)],
        })
    grid = []
    for score in [0, 3, 4.5, 6, 7.5, 9]:
        y = top + usable_h - (score / 9.0) * usable_h
        grid.append({"score": score, "y": y})
    x_labels = [
        {"label": day["short"], "x": left + (usable_w * i / max(1, len(chart_dates) - 1))}
        for i, day in enumerate(chart_dates)
    ]
    return {"width": width, "height": height, "series": series, "grid": grid, "x_labels": x_labels}


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


def inline_result_from_record_data(data):
    data = data if isinstance(data, dict) else {}
    result_data = data.get("result_data")
    score = data.get("score")
    if isinstance(result_data, dict):
        score = result_data.get("overall_score") or score
    return {
        "mode": data.get("mode", ""),
        "result": data.get("result", ""),
        "result_data": result_data if isinstance(result_data, dict) else None,
        "user_response": data.get("user_response", "") or data.get("transcript", ""),
        "transcript": data.get("transcript", ""),
        "audio_file": data.get("audio_file", ""),
        "recorded_at": data.get("recorded_at", ""),
        "transcript_source": data.get("transcript_source", ""),
        "score": score,
        "chinese_answer": data.get("chinese_answer", ""),
        "keywords": data.get("keywords", ""),
    }


def attach_replay_inline_result(parent_data, source_mode, question, inline):
    if not isinstance(parent_data, dict) or not isinstance(inline, dict):
        return parent_data
    source_mode = source_mode if source_mode in {"part1", "part2", "part3"} else infer_record_mode({"data": parent_data})
    question_key = _normalized_question(question)
    if source_mode == "part2":
        parent_data["_inline_result"] = inline
    elif source_mode == "part3" and isinstance(parent_data.get("discussion_questions"), list):
        target = None
        for item in parent_data["discussion_questions"]:
            if isinstance(item, dict) and _normalized_question(item.get("question", "")) == question_key:
                target = item
                break
        if target is None and parent_data["discussion_questions"]:
            target = parent_data["discussion_questions"][0]
        if isinstance(target, dict):
            target["_inline_result"] = inline
    elif isinstance(parent_data.get("questions"), list):
        target = None
        for item in parent_data["questions"]:
            if isinstance(item, dict) and _normalized_question(item.get("question", "")) == question_key:
                target = item
                break
        if target is None and parent_data["questions"]:
            target = parent_data["questions"][0]
        if isinstance(target, dict):
            target["_inline_result"] = inline
    mark_speaking_focus(parent_data, source_mode)
    return parent_data


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


def compact_speaking_context(value):
    if isinstance(value, dict):
        compact = {}
        for key, item in value.items():
            if key.startswith("_") or key in {"_feedbacks", "_related_records"}:
                continue
            compact[key] = compact_speaking_context(item)
        return compact
    if isinstance(value, list):
        return [compact_speaking_context(item) for item in value]
    return value


@app.template_filter("speaking_source_context")
def speaking_source_context_filter(value):
    return compact_speaking_context(value)


def fallback_speaking_parent_data(source_mode, question):
    question = (question or "").strip() or "Please answer this IELTS speaking question."
    if source_mode == "part2":
        return {"cue_card": question}
    if source_mode == "part3":
        return {"discussion_questions": [{"question": question}]}
    return {"questions": [{"question": question}]}


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
        question_index = request.form.get("question_index", "").strip() if has_request_context() else ""
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


def _criterion_score(value):
    if isinstance(value, dict):
        for key in ("score", "band_score", "overall_score", "分数"):
            score = normalize_ielts_score(value.get(key))
            if score is not None:
                return score
    return normalize_ielts_score(value)


@app.template_filter("speaking_score_preview")
def speaking_score_preview_filter(result_data):
    criteria_config = [
        (
            "fluency",
            "流利度与连贯性",
            ["fluency_coherence", "fluency_and_coherence", "fluency", "流利度与连贯性"],
        ),
        (
            "lexical",
            "词汇资源",
            ["lexical_resource", "vocabulary", "lexical", "词汇资源"],
        ),
        (
            "grammar",
            "语法多样性与准确性",
            ["grammatical_range_accuracy", "grammar_range_accuracy", "grammar", "语法"],
        ),
        (
            "pronunciation",
            "发音表现",
            ["pronunciation", "pronunciation_score", "发音", "发音表现"],
        ),
    ]
    preview = {
        "overall": None,
        "criteria": [{"key": key, "label": label, "score": None} for key, label, _ in criteria_config],
    }
    if not isinstance(result_data, dict):
        return preview

    for key in ("overall_score", "score", "band_score", "overall_band", "总分"):
        score = normalize_ielts_score(result_data.get(key))
        if score is not None:
            preview["overall"] = score
            break

    breakdown = result_data.get("breakdown")
    for item in preview["criteria"]:
        _, _, aliases = next(cfg for cfg in criteria_config if cfg[0] == item["key"])
        score = None
        if isinstance(breakdown, dict):
            for alias in aliases:
                score = _criterion_score(breakdown.get(alias))
                if score is not None:
                    break
        elif isinstance(breakdown, list):
            for entry in breakdown:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("criterion") or entry.get("name") or entry.get("title") or "")
                if any(alias.lower() in name.lower() for alias in aliases):
                    score = _criterion_score(entry)
                    break
        if score is None:
            for alias in aliases:
                score = _criterion_score(result_data.get(alias))
                if score is not None:
                    break
        item["score"] = score

    scores = [item["score"] for item in preview["criteria"] if item["score"] is not None]
    if preview["overall"] is None and scores:
        preview["overall"] = round((sum(scores) / len(scores)) * 2) / 2
    return preview


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


def writing_criteria_keys(task_type):
    return (
        ["task_achievement", "coherence_cohesion", "lexical_resource", "grammatical_range"]
        if task_type == "Task 1"
        else ["task_response", "coherence_cohesion", "lexical_resource", "grammatical_range"]
    )


def normalize_writing_scores(feedback_data, task_type):
    if not isinstance(feedback_data, dict):
        return feedback_data
    scores = []
    for key in writing_criteria_keys(task_type):
        item = feedback_data.get(key)
        if not isinstance(item, dict):
            continue
        score = normalize_ielts_score(item.get("score"))
        if score is not None:
            item["score"] = score
            scores.append(score)
    if scores:
        feedback_data["overall_score"] = round((sum(scores) / len(scores)) * 2) / 2
    else:
        score = normalize_ielts_score(feedback_data.get("overall_score"))
        if score is not None:
            feedback_data["overall_score"] = score
    return feedback_data


def reference_essay_note_for_submission(essay_content):
    stored = session.get("latest_model_answer", "")
    if not stored:
        return "无"
    response = _normalized_answer_text(essay_content)
    reference = _normalized_answer_text(stored)
    if len(response) < 120 or len(reference) < 120:
        return "无"
    shorter = min(len(response), len(reference))
    contains = shorter >= 120 and (response in reference or reference in response)
    similarity = SequenceMatcher(None, response, reference).ratio()
    if contains or similarity >= 0.88:
        return "考生作文与平台刚生成的 Band 8.0-8.5 高分参考范文高度一致，请按高分参考范文标准评分。"
    return "无"


def calibrate_reference_essay_scores(feedback_data, task_type, reference_note):
    if not isinstance(feedback_data, dict) or reference_note == "无":
        return feedback_data
    adjusted = False
    for key in writing_criteria_keys(task_type):
        item = feedback_data.get(key)
        if not isinstance(item, dict):
            continue
        score = normalize_ielts_score(item.get("score"))
        if score is not None and 0 < score < 7.5:
            item["score"] = 7.5
            adjusted = True
    feedback_data = normalize_writing_scores(feedback_data, task_type)
    overall = normalize_ielts_score(feedback_data.get("overall_score"))
    if adjusted or (overall is not None and 0 < overall < 7.5):
        feedback_data["overall_score"] = max(7.5, overall or 7.5)
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


def clean_transcribe_error(error):
    message = str(error or "").strip()
    if not message:
        return "语音识别服务暂时不可用。"
    lowered = message.lower()
    if "<html" in lowered or "<!doctype" in lowered:
        status_match = re.search(r"\b(4\d\d|5\d\d)\b", message)
        if status_match:
            status = status_match.group(1)
            if status == "404":
                return "语音识别接口地址不支持当前转写请求。"
            return f"语音识别接口返回 HTTP {status}。"
        return "语音识别接口返回了错误页面。"
    message = re.sub(r"<[^>]+>", " ", message)
    message = re.sub(r"\s+", " ", message).strip()
    message = message.replace("Not Found", "接口不存在")
    message = message.replace("Unauthorized", "API Key 无效或权限不足")
    message = message.replace("Forbidden", "API Key 没有语音识别权限")
    return message[:160] + ("..." if len(message) > 160 else "")


def transcribe_audio_file_with_api(ai_config, audio_path):
    return "", ""


def transcribe_audio_file(ai_config, audio_path):
    local_text, local_error = transcribe_audio_file_locally(audio_path)
    if local_text:
        return local_text, "", "local"
    guidance = "请检查录音音量、麦克风权限，或直接在文本框输入回答后获取评分。"
    return "", " ".join([item for item in [local_error, guidance] if item]).strip(), ""



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
    scheme = forwarded_proto or ("https" if request.is_secure else (request.scheme or "http"))
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
    scheme = parts.scheme or request.scheme or "http"
    # Ensure the scheme matches the current request so HTTPS pages link to HTTPS
    if request.is_secure:
        scheme = "https"
    return urlunsplit((scheme, netloc, "", "", "")).rstrip("/")


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
                "found": True,
            }
    return {
        "word": word,
        "translation": "暂未在内置词库中找到，可保存到生词本后继续复习。",
        "phrases": [],
        "usage": "建议结合上下文判断词性和含义，再用 AI 查询更完整的作文用法。",
        "source": "临时查询",
        "found": False,
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
    all_progress = list(reversed(get_progress(user_id, limit=180)))
    auto_guidance = maybe_auto_refresh_learning_guidance(user_id, tracked_profile, all_progress)
    if auto_guidance.get("suggestions") or auto_guidance.get("study_plan"):
        all_progress = list(reversed(get_progress(user_id, limit=180)))
    suggestion_record = get_latest_progress_by_activity(user_id, IMPROVEMENT_SUGGESTIONS_ACTIVITY)
    study_plan_record = get_latest_progress_by_activity(user_id, STUDY_PLAN_ACTIVITY)
    suggestions = latest_saved_suggestions([suggestion_record] if suggestion_record else [])
    study_plan = latest_saved_study_plan([study_plan_record] if study_plan_record else [])
    prepared_progress = prepare_progress(all_progress)
    study_plan = ensure_exam_daily_schedule(tracked_profile, study_plan, prepared_progress)
    prepared_progress.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
    total_records = len(prepared_progress)
    progress = prepared_progress[:4]
    context = common_context()
    context["profile"] = tracked_profile
    context["level_tracking"] = tracked_profile.get("_tracking", {})
    context["skill_scores"] = skill_score_overview(tracked_profile)
    context["goal_progress"] = dashboard_goal_progress(prepared_progress)
    context["exam_countdown"] = exam_countdown(tracked_profile)
    context["ability_trend_chart"] = ability_trend_chart(all_progress, tracked_profile)
    context["guidance_overview"] = learning_guidance_overview(tracked_profile, prepared_progress, suggestions, study_plan)
    context["auto_guidance"] = auto_guidance
    return render_template(
        "dashboard.html",
        progress=progress,
        page=1,
        total_pages=1,
        total_records=total_records,
        suggestions=suggestions,
        study_plan=study_plan,
        date_filter="",
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
    try:
        suggestions = save_ai_suggestions(user_id, profile, progress)
    except Exception as exc:
        flash(f"AI 调用失败：{exc}", "error")
        return redirect(url_for("dashboard"))
    if suggestions is not None:
        flash("重点提升建议已生成。", "success")
    return redirect(url_for("dashboard"))


@app.post("/generate-study-plan")
@login_required
def generate_study_plan():
    user_id = session["user_id"]
    profile = load_user_profile(user_id) or default_profile(user_id)
    progress = prepare_progress(list(reversed(get_progress(user_id, limit=100))))
    try:
        study_plan = save_ai_study_plan(user_id, profile, progress)
    except Exception as exc:
        flash(f"AI 调用失败：{exc}", "error")
        return redirect(request.referrer or url_for("dashboard"))
    if study_plan is not None:
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
        "daily_vocab_goal": clamp_int(request.form.get("daily_vocab_goal"), 30, 5, 300),
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
    existing = load_user_ai_config(user_id)
    api_keys = dict(existing.get("api_keys", {}))
    touched_marker_present = "api_key_touched" in request.form
    touched_keys = {
        item.strip()
        for item in request.form.get("api_key_touched", "").split(",")
        if item.strip()
    }
    api_key = request.form.get("api_key", "").strip()
    if api_key and ((not touched_marker_present) or provider in touched_keys):
        api_keys[provider] = api_key
    for key in AI_PROVIDERS:
        value = request.form.get(f"api_key_{key}", "").strip()
        if value and ((not touched_marker_present) or key in touched_keys):
            api_keys[key] = value
    model = request.form.get("model", "").strip() or defaults["model"]
    base_url = request.form.get("base_url", "").strip() or defaults["base_url"]
    model_usage = classify_model_usage(model)
    if model_usage["recommended_for"] != "text":
        fallback_model = defaults["model"]
        flash(f"{model} 是{model_usage['label']}，不适合生成题目/批改，已自动改用 {fallback_model}。朗读请在下方 TTS 模块配置。", "error")
        model = fallback_model

    if not api_keys.get(provider):
        flash("请输入该模型供应商的 API Key。", "error")
        return redirect(url_for("settings_page"))

    save_user_ai_config_map(user_id, provider, api_keys, model, base_url)
    flash("AI 模型配置已保存。", "success")
    return redirect(url_for("settings_page"))


@app.post("/tts-config")
@login_required
def update_tts_config():
    provider = request.form.get("tts_provider", "").strip()
    if not provider:
        save_user_tts_config(session["user_id"], "", "", "", "", False)
        flash("已关闭云端 TTS，将使用浏览器朗读作为兜底。", "success")
        return redirect(url_for("settings_page"))

    defaults = AI_PROVIDERS.get(provider, {})
    ai_config = load_user_ai_config(session["user_id"])
    api_key = ai_config.get("api_keys", {}).get(provider, "")
    if not api_key:
        flash("请先在上方保存该 TTS 供应商的 API Key，再验证语音朗读。", "error")
        return redirect(url_for("settings_page"))

    model = request.form.get("tts_model", "").strip() or ("mimo-v2.5-tts" if provider == "mimo" else "gpt-4o-mini-tts")
    base_url = request.form.get("tts_base_url", "").strip() or defaults.get("base_url", "")
    voice = request.form.get("tts_voice", "").strip() or ("Chloe" if provider == "mimo" else "coral")
    try:
        audio_bytes, _, used_voice, _ = synthesize_tts_audio(
            provider,
            api_key,
            model,
            base_url,
            voice,
            "This is a TTS validation for Xindaya IELTS practice.",
        )
        if len(audio_bytes) < 256:
            raise RuntimeError("测试音频过短，可能不是有效音频")
    except Exception as exc:
        save_user_tts_config(session["user_id"], "", "", "", "", False)
        flash(f"语音朗读验证失败，已禁用云端 TTS：{exc}", "error")
        return redirect(url_for("settings_page"))

    save_user_tts_config(
        session["user_id"],
        provider,
        model,
        base_url,
        used_voice,
        True,
    )
    flash(f"语音朗读验证通过，已启用 {AI_PROVIDERS.get(provider, {}).get('label', provider)} · {model} · {used_voice}。", "success")
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


@app.post("/api/ai-models")
@login_required
def api_ai_models():
    payload = request.get_json(silent=True) or request.form
    provider = (payload.get("provider") or "custom").strip()
    api_key = (payload.get("api_key") or "").strip()
    base_url = (payload.get("base_url") or "").strip()
    if not api_key:
        api_key = load_user_ai_config(session["user_id"]).get("api_keys", {}).get(provider, "")
    models, error = fetch_provider_models(provider, api_key, base_url)
    return jsonify({"ok": not bool(error), "models": models, "model_options": describe_models(models), "error": error})


@app.post("/api/tts-models")
@login_required
def api_tts_models():
    payload = request.get_json(silent=True) or request.form
    provider = (payload.get("provider") or "").strip()
    api_key = (payload.get("api_key") or "").strip()
    base_url = (payload.get("base_url") or "").strip()
    if not provider:
        return jsonify({"ok": False, "models": [], "voices": [], "error": "请选择 TTS 供应商。"})
    if not api_key:
        api_key = load_user_ai_config(session["user_id"]).get("api_keys", {}).get(provider, "")
    models, error = fetch_provider_models(provider, api_key, base_url)
    options = [item for item in describe_models(models) if item["recommended_for"] == "tts"]
    if not options and provider == "mimo":
        options = [{"id": "mimo-v2.5-tts", **classify_model_usage("mimo-v2.5-tts")}]
    elif not options and provider == "openai":
        options = [{"id": "gpt-4o-mini-tts", **classify_model_usage("gpt-4o-mini-tts")}]
    return jsonify({
        "ok": not bool(error) or bool(options),
        "models": [item["id"] for item in options],
        "model_options": options,
        "voices": default_tts_voices(provider),
        "error": "" if options else error,
    })


@app.post("/api/ai-test")
@login_required
def api_ai_test():
    payload = request.get_json(silent=True) or request.form
    provider = (payload.get("provider") or "custom").strip()
    api_key = (payload.get("api_key") or "").strip()
    model = (payload.get("model") or "").strip()
    base_url = (payload.get("base_url") or "").strip()
    if not api_key:
        api_key = load_user_ai_config(session["user_id"]).get("api_keys", {}).get(provider, "")
    ok, message = test_provider_connection(provider, api_key, model, base_url)
    return jsonify({"ok": ok, "message": message})


@app.get("/api/tts-status")
@login_required
def api_tts_status():
    ai_config = load_user_ai_config(session["user_id"])
    provider = (ai_config.get("tts_provider") or "").lower()
    model = ai_config.get("tts_model") or ""
    voice = ai_config.get("tts_voice") or ""
    api_key = ai_config.get("api_keys", {}).get(provider, "") if provider else ""
    enabled = bool(provider and api_key and ai_config.get("tts_validated"))
    return jsonify({
        "enabled": enabled,
        "provider": provider,
        "provider_label": AI_PROVIDERS.get(provider, {}).get("label", provider),
        "model": model,
        "voice": voice,
    })


@app.post("/api/tts")
@login_required
def api_tts():
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "没有可朗读的文本。"}), 400
    if len(text) > 4000:
        text = text[:4000]
    ai_config = load_user_ai_config(session["user_id"])
    provider = (ai_config.get("tts_provider") or "").lower()
    if not provider:
        return jsonify({"ok": False, "error": "未配置 TTS 模型。"}), 400
    if not ai_config.get("tts_validated"):
        return jsonify({"ok": False, "error": "当前 TTS 配置尚未通过后台验证，请先到用户中心测试并保存。"}), 400
    api_key = ai_config.get("api_keys", {}).get(provider, "")
    if not api_key:
        return jsonify({"ok": False, "error": "未保存该 TTS 供应商的 API Key。"}), 400
    model = ai_config.get("tts_model") or ("mimo-v2.5-tts" if provider == "mimo" else "gpt-4o-mini-tts")
    base_url = ai_config.get("tts_base_url") or AI_PROVIDERS.get(provider, {}).get("base_url", "")
    voice = ai_config.get("tts_voice") or "alloy"
    try:
        audio_bytes, mimetype, used_voice, attempted = synthesize_tts_audio(provider, api_key, model, base_url, voice, text)
        flask_response = app.response_class(audio_bytes, mimetype=mimetype)
        flask_response.headers["X-TTS-Provider"] = provider
        flask_response.headers["X-TTS-Model"] = model
        flask_response.headers["X-TTS-Voice"] = used_voice
        flask_response.headers["X-TTS-Voices-Tried"] = ",".join(attempted)
        return flask_response
    except Exception as exc:
        provider_label = AI_PROVIDERS.get(provider, {}).get("label", provider)
        save_user_tts_config(session["user_id"], "", "", "", "", False)
        return jsonify({
            "ok": False,
            "error": f"云端 TTS 调用失败，已自动禁用该配置：{exc}",
            "provider": provider_label,
            "model": model,
            "base_url": base_url,
        }), 502


@app.route("/admin")
@admin_required
def admin_panel():
    selected_user = request.args.get("user_id", "").strip()
    users = list_users()
    for item in users:
        item["is_admin"] = bool(item.get("is_admin")) or is_admin_user(item.get("user_id"))
    users.sort(key=lambda item: (not item.get("is_admin"), str(item.get("user_id", "")).lower()))
    admin_count = sum(1 for item in users if item.get("is_admin"))
    total_user_records = sum(int(item.get("record_count") or 0) for item in users)
    selected_profile = load_user_profile(selected_user) if selected_user else None
    selected_ai_config = load_user_ai_config(selected_user) if selected_user else None
    selected_is_admin = is_admin_user(selected_user) if selected_user else False
    records = prepare_progress(get_all_progress(limit=500, user_id=selected_user))
    for item in records:
        summary = item.get("progress_summary") if isinstance(item.get("progress_summary"), dict) else {}
        score = item.get("display_score")
        if score is None:
            score = score_from_progress_record(item)
        if score is None:
            score = summary.get("score")
        item["admin_score"] = score
    records.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
    return render_template(
        "admin.html",
        users=users,
        records=records,
        admin_count=admin_count,
        total_user_records=total_user_records,
        selected_user=selected_user,
        selected_profile=selected_profile,
        selected_ai_config=selected_ai_config,
        selected_is_admin=selected_is_admin,
        score_options=score_options(),
        target_options=score_options(4.0, 9.0),
        **common_context(),
    )


@app.route("/admin/vocabulary")
@admin_required
def admin_vocabulary():
    query = request.args.get("q", "").strip().lower()
    topic = request.args.get("topic", "")
    status = request.args.get("status", "needs")
    page = int_query("page", 1)
    per_page = 40
    words = [dict(item) for item in IELTS_WORDS]
    for item in words:
        item["has_chinese_meaning"] = _has_chinese_meaning(item)
        item["needs_enrichment"] = _needs_vocab_enrichment(item)
    if query:
        words = [
            item for item in words
            if query in item.get("word", "").lower()
            or query in item.get("meaning", "").lower()
            or query in item.get("topic", "").lower()
        ]
    if topic:
        words = [item for item in words if item.get("topic") == topic]
    if status == "needs":
        words = [item for item in words if item.get("needs_enrichment")]
    elif status == "complete":
        words = [item for item in words if not item.get("needs_enrichment")]
    total_words = len(IELTS_WORDS)
    needs_count = sum(1 for item in IELTS_WORDS if _needs_vocab_enrichment(item))
    phonetic_count = sum(1 for item in IELTS_WORDS if item.get("phonetic"))
    chinese_count = sum(1 for item in IELTS_WORDS if _has_chinese_meaning(item))
    topics = sorted({item.get("topic", "通用学术词") for item in IELTS_WORDS})
    total_pages = max(1, math.ceil(len(words) / per_page))
    page = max(1, min(page, total_pages))
    page_words = words[(page - 1) * per_page:page * per_page]
    selected_word = request.args.get("word", "").strip().lower()
    selected_item = next((item for item in IELTS_WORDS if item.get("word", "").lower() == selected_word), None)
    return render_template(
        "admin_vocabulary.html",
        words=page_words,
        selected_item=selected_item,
        query=query,
        topic=topic,
        status=status,
        topics=topics,
        page=page,
        total_pages=total_pages,
        page_items=pagination_window(page, total_pages),
        total_words=total_words,
        needs_count=needs_count,
        phonetic_count=phonetic_count,
        chinese_count=chinese_count,
        **common_context(),
    )


@app.post("/admin/vocabulary/bulk-enrich")
@admin_required
def admin_bulk_enrich_vocabulary():
    assistant, _ = current_assistant()
    if assistant is None:
        flash("请先在管理员账号的用户中心保存可用 API Key。", "error")
        return redirect(url_for("admin_vocabulary"))
    limit = clamp_int(request.form.get("limit"), 10, 1, 80)
    candidates = [item for item in IELTS_WORDS if _needs_vocab_enrichment(item)][:limit]
    success = 0
    failed = []
    for item in candidates:
        try:
            _enrich_vocab_item(assistant, item)
            success += 1
        except Exception as exc:
            failed.append(f"{item.get('word')}: {exc}")
    if success:
        flash(f"已补全 {success} 个词条。", "success")
    if failed:
        flash("部分词条补全失败：" + "；".join(failed[:3]), "error")
    if not candidates:
        flash("当前没有待补全词条。", "success")
    return redirect(url_for("admin_vocabulary"))


@app.post("/admin/vocabulary/<word>/save")
@admin_required
def admin_save_vocabulary_word(word):
    phrases = [
        item.strip()
        for item in request.form.get("phrases", "").replace("\n", ",").split(",")
        if item.strip()
    ]
    enrichment = {
        "meaning": request.form.get("meaning", "").strip(),
        "phonetic": request.form.get("phonetic", "").strip(),
        "topic": request.form.get("topic", "").strip() or "通用学术词",
        "phrases": phrases[:8],
        "essay_use": request.form.get("essay_use", "").strip(),
    }
    if not enrichment["meaning"]:
        flash("中文释义不能为空。", "error")
    else:
        _save_vocab_ai_override(word, enrichment)
        flash(f"{word} 词条已保存。", "success")
    return redirect(url_for("admin_vocabulary", word=word, status=request.form.get("status", "needs")))


@app.post("/admin/vocabulary/<word>/enrich")
@admin_required
def admin_enrich_vocabulary_word(word):
    assistant, _ = current_assistant()
    if assistant is None:
        flash("请先在管理员账号的用户中心保存可用 API Key。", "error")
        return redirect(url_for("admin_vocabulary", word=word, status=request.form.get("status", "needs")))
    target = next((item for item in IELTS_WORDS if item.get("word", "").lower() == word.lower()), None)
    if not target:
        flash("词库中未找到这个单词。", "error")
    else:
        try:
            _enrich_vocab_item(assistant, target)
            flash(f"{target.get('word')} 已用 AI 补全。", "success")
        except Exception as exc:
            flash(f"AI 补全失败：{exc}", "error")
    return redirect(url_for("admin_vocabulary", word=word, status=request.form.get("status", "needs")))


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
        "daily_vocab_goal": clamp_int(request.form.get("daily_vocab_goal"), 30, 5, 300),
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
        if ai_config.get("used_model_fallback"):
            flash(f"当前选择的 {ai_config.get('requested_model')} 不适合文本生成，已自动改用 {ai_config.get('effective_model')}。", "success")

        if mode == "writing_ideas":
            topic = request.form.get("topic", "").strip()
            question = request.form.get("question", "").strip()
            try:
                result = assistant.generate_writing_ideas(topic, question)
            except Exception as exc:
                flash(f"AI 调用失败：{exc}", "error")
                return redirect(url_for("assistant_center"))
            save_progress(session["user_id"], "作文思路互动", {"topic": topic, "question": question})

        elif mode == "speaking_part2":
            topic = request.form.get("speaking_topic", "人物描述")
            cue_type = request.form.get("cue_type", "描述类")
            try:
                result = assistant.practice_speaking_part2(topic, cue_type)
            except Exception as exc:
                flash(f"AI 调用失败：{exc}", "error")
                return redirect(url_for("assistant_center"))
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
        if ai_config.get("used_model_fallback"):
            flash(f"当前选择的 {ai_config.get('requested_model')} 不适合文本生成，已自动改用 {ai_config.get('effective_model')}。", "success")
        if mode == "part1":
            topic = request.form.get("topic", "工作/学习")
            difficulty = request.form.get("difficulty", "中等")
            try:
                result = assistant.practice_speaking_part1(
                    topic,
                    difficulty,
                )
            except Exception as exc:
                flash(f"AI 生成题目失败：{exc}", "error")
                return redirect(url_for("speaking", mode=mode))
            result_data = parse_model_output(result)
            result_data = sanitize_speaking_result(mode, result_data)
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
            try:
                result = assistant.practice_speaking_part2(
                    topic,
                    cue_type,
                )
            except Exception as exc:
                flash(f"AI 生成题目失败：{exc}", "error")
                return redirect(url_for("speaking", mode=mode))
            result_data = parse_model_output(result)
            result_data = sanitize_speaking_result(mode, result_data)
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
            try:
                result = assistant.practice_speaking_part3(
                    part2_topic,
                    discussion_type,
                )
            except Exception as exc:
                flash(f"AI 生成题目失败：{exc}", "error")
                return redirect(url_for("speaking", mode=mode))
            result_data = parse_model_output(result)
            result_data = sanitize_speaking_result(mode, result_data)
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
            # Text-only feedback must not attach any historical recording.
            # Recordings are bound to a question only through /api/speech-score.
            audio_file = ""
            save_progress(session["user_id"], "口语反馈", {
                "mode": mode,
                "question": question,
                "user_response": user_response,
                "score": score_value,
                "result": result,
                "result_data": result_data,
                "audio_file": audio_file,
                "source_mode": source_mode,
                "source_result_data": parent_data,
            })
            refresh_user_level_tracking(session["user_id"])
            parent_with_inline = attach_inline_speaking_result(
                parent_data or fallback_speaking_parent_data(source_mode, question),
                source_mode,
                mode,
                question,
                result,
                result_data,
                {"score": score_value,
                 "audio_file": audio_file,
                 "user_response": user_response,
                },
            )
            if parent_with_inline is not None:
                render_result = json.dumps(parent_with_inline, ensure_ascii=False)
                render_result_data = parent_with_inline
                render_mode = source_mode
        elif mode == "keyword_answer":
            question = request.form.get("question", "").strip()
            keywords = request.form.get("keywords", "").strip()
            part = request.form.get("part", "Part 2")
            source_mode = speaking_source_mode_from_form(mode)
            parent_data = speaking_parent_data_from_form()
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
                "source_mode": source_mode,
                "source_result_data": parent_data,
            })
            parent_with_inline = attach_inline_speaking_result(
                parent_data or fallback_speaking_parent_data(source_mode, question),
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
            source_mode = speaking_source_mode_from_form(mode)
            parent_data = speaking_parent_data_from_form()
            result = assistant.generate_answer_from_cn(question, chinese_answer)
            save_progress(session["user_id"], "中文思路生成英文口语答案", {
                "mode": mode,
                "question": question,
                "chinese_answer": chinese_answer,
                "result": result,
                "source_mode": source_mode,
                "source_result_data": parent_data,
            })
            parent_with_inline = attach_inline_speaking_result(
                parent_data or fallback_speaking_parent_data(source_mode, question),
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
            if render_result is not None:
                # Inline-result action (feedback / keyword / cn-answer).
                # Render the current question set directly. Putting the full
                # question payload plus feedback into Flask's client-side
                # session can exceed cookie limits, especially for replayed
                # Part 2 records, which makes the GET fallback show a blank
                # initial Part 2 page.
                session.pop("_speaking_replay_id", None)
                current_mode = render_mode or mode
                if isinstance(render_result_data, dict) and current_mode in {"part1", "part2", "part3"}:
                    render_result_data = sanitize_speaking_result(current_mode, render_result_data)
                    render_result_data = decorate_current_speaking_result(session["user_id"], render_result_data)
                    render_result = json.dumps(render_result_data, ensure_ascii=False)
                return render_template(
                    "speaking.html",
                    result=render_result,
                    result_data=render_result_data,
                    mode=current_mode,
                    **common_context(),
                )
            session["speaking_result"] = result
            session["speaking_result_data"] = (
                json.dumps(result_data, ensure_ascii=False)
                if result_data is not None else None
            )
            session["speaking_mode"] = mode
    else:
        replay_record = replay_record_from_args()
        if not replay_record:
            try:
                hint_id = session.pop("_speaking_replay_id", "")
                if hint_id:
                    progress = get_progress(session["user_id"], limit=50)
                    for p in progress:
                        if str(p.get("id")) == str(hint_id):
                            replay_record = p
                            break
            except Exception:
                pass
        if replay_record:
            replay_mode = infer_record_mode(replay_record) or mode
            if replay_mode == "speaking_recording":
                mode, result_data = speaking_record_replay_payload(replay_record)
                result = json.dumps(result_data, ensure_ascii=False)
            elif replay_mode in {"speaking_feedback", "keyword_answer", "answer_from_cn"}:
                # Inline action records may be replayed directly from history.
                # Prefer their saved parent question payload; for older records
                # that lack it, rebuild a minimal current-question page.
                feedback_data = replay_record.get("data") or {}
                source_mode = feedback_data.get("source_mode") or ""
                question = feedback_data.get("question") or ""
                mode, result_data = speaking_record_replay_payload(replay_record)
                if source_mode in {"part1", "part2", "part3"}:
                    mode = source_mode
                if not isinstance(result_data, dict) or not question:
                    result_data = fallback_speaking_parent_data(mode, question)
                result_data = attach_replay_inline_result(
                    result_data,
                    mode,
                    question,
                    inline_result_from_record_data(feedback_data),
                )
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
        result_data = sanitize_speaking_result(mode, result_data)
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
    writing_form_task = ""
    writing_form_topic = ""
    writing_form_essay = ""
    writing_form_topic_category = ""
    writing_form_essay_type = ""
    writing_form_task_type = ""
    assistant, ai_config = current_assistant()
    if request.method == "POST":
        if assistant is None:
            flash("请先在用户中心保存可用的 AI API Key。", "error")
            return redirect(url_for("dashboard"))
        if ai_config.get("used_model_fallback"):
            flash(f"当前选择的 {ai_config.get('requested_model')} 不适合文本生成，已自动改用 {ai_config.get('effective_model')}。", "success")
        if mode == "generate_topic":
            task_type = request.form.get("task_type", "Task 2")
            chart_type = request.form.get("chart_type", "柱状图")
            topic = request.form.get("topic", "教育")
            try:
                result = assistant.generate_writing_topic(task_type, chart_type=chart_type, topic=topic)
            except Exception as exc:
                flash(f"AI 生成作文题目失败：{exc}", "error")
                return redirect(url_for("writing", mode="task1" if task_type == "Task 1" else "task2"))
            result_data = parse_generated_topic_md(result, task_type)
            result_data = build_task1_chart_assets(result_data, raw_text=result)
            session["generated_topic_text"] = result_data.get("question", "")
            session["generated_topic_task"] = task_type
            # 同步生成参考范文
            topic_q = result_data.get("question", "")
            if topic_q:
                try:
                    model_answer = assistant.generate_model_answer(
                        task_type, topic_q,
                        result_data.get("chart_type", ""),
                        result_data.get("chart_data"),
                        result_data.get("table_data"),
                    )
                    result_data["model_answer"] = sanitize_writing_model_answer(task_type, model_answer)
                except Exception:
                    pass
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
                "model_answer": result_data.get("model_answer", ""),
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
                "task_type": session.get("generated_topic_task", "Task 2"),
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
            topic = request.form.get("topic", "").strip()
            writing_form_task = "Task 1"
            writing_form_topic = topic
            writing_form_essay = essay_content
            writing_form_task_type = task_type
            target_score = float_field("target_score", 6.5)
            reference_note = reference_essay_note_for_submission(essay_content)
            result = assistant.correct_writing_task1(
                task_type,
                essay_content,
                target_score,
                topic=topic,
            )
            result_data = parse_model_output(result)
            result_data = normalize_writing_scores(result_data, "Task 1")
            result_data = calibrate_reference_essay_scores(result_data, "Task 1", reference_note)
            if isinstance(result_data, dict):
                result_data["_essay_content"] = essay_content
            save_progress(session["user_id"], "写作 Task 1 批改", {
                "mode": mode,
                "task_type": task_type,
                "topic": topic,
                "question": topic,
                "essay_content": essay_content,
                "target_score": target_score,
                "score": result_data.get("overall_score") if isinstance(result_data, dict) else None,
                "result": result,
                "result_data": result_data,
            })
            refresh_user_level_tracking(session["user_id"])
        elif mode == "task2":
            topic_category = request.form.get("topic_category", "教育")
            topic = request.form.get("topic", "").strip()
            essay_type = request.form.get("essay_type", "议论文")
            essay_content = request.form.get("essay_content", "")
            writing_form_task = "Task 2"
            writing_form_topic = topic
            writing_form_essay = essay_content
            writing_form_topic_category = topic_category
            writing_form_essay_type = essay_type
            target_score = float_field("target_score", 6.5)
            reference_note = reference_essay_note_for_submission(essay_content)
            result = assistant.correct_writing_task2(
                topic or topic_category,
                essay_type,
                essay_content,
                target_score,
            )
            result_data = parse_model_output(result)
            result_data = normalize_writing_scores(result_data, "Task 2")
            result_data = calibrate_reference_essay_scores(result_data, "Task 2", reference_note)
            if isinstance(result_data, dict):
                result_data["_essay_content"] = essay_content
            save_progress(session["user_id"], "写作 Task 2 批改", {
                "mode": mode,
                "topic_category": topic_category,
                "essay_type": essay_type,
                "topic": topic,
                "question": topic,
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
            result = sanitize_writing_model_answer(task_type, result)
            session["latest_model_answer"] = result
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
            session["inline_model_answer"] = result
            flash("参考范文已生成，显示在题目下方。", "success")
            return redirect(url_for("writing"))
        if result is not None:
            session["writing_result"] = result
            session["writing_result_data"] = json.dumps(result_data) if result_data is not None else None
            session["writing_mode"] = mode
    else:
        replay_record = replay_record_from_args()
        if replay_record:
            mode = infer_record_mode(replay_record) or mode
            result, result_data = result_from_record(replay_record)
            data = replay_record.get("data") or {}
            if mode in {"task1", "task2"}:
                writing_form_task = "Task 1" if mode == "task1" else "Task 2"
                writing_form_topic = (data.get("question") or data.get("topic") or "").strip()
                writing_form_essay = data.get("essay_content", "")
                writing_form_topic_category = data.get("topic_category", "")
                writing_form_essay_type = data.get("essay_type", "")
                writing_form_task_type = data.get("task_type", "")
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
    generated_topic_data = {}
    stored_generated_topic = session.get("generated_chart_data", "")
    if stored_generated_topic:
        try:
            generated_topic_data = json.loads(stored_generated_topic)
        except (TypeError, ValueError):
            generated_topic_data = {}
    if isinstance(generated_topic_data, dict) and generated_topic_data.get("model_answer"):
        task_for_answer = generated_topic_data.get("task_type", "Task 2")
        generated_topic_data["model_answer"] = sanitize_writing_model_answer(
            task_for_answer,
            generated_topic_data.get("model_answer", ""),
        )
        session["generated_chart_data"] = json.dumps(generated_topic_data, ensure_ascii=False)
    if isinstance(result_data, dict) and mode == "generate_topic" and result_data.get("model_answer"):
        result_data["model_answer"] = sanitize_writing_model_answer(
            result_data.get("task_type", "Task 2"),
            result_data.get("model_answer", ""),
        )

    # 内联参考范文（从 generate_model_answer 重定向回来时）
    inline_model_answer = session.pop("inline_model_answer", None)

    return render_template("writing.html",
        result=result, result_data=result_data, mode=mode,
        import_question=import_question,
        import_task=import_task,
        import_topic=import_topic,
        ideas_topic=ideas_topic,
        ideas_question=ideas_question,
        generated_topic_text=gen_topic_text,
        generated_topic_task=gen_topic_task,
        generated_topic_data=generated_topic_data,
        inline_model_answer=inline_model_answer,
        writing_form_task=writing_form_task,
        writing_form_topic=writing_form_topic,
        writing_form_essay=writing_form_essay,
        writing_form_topic_category=writing_form_topic_category,
        writing_form_essay_type=writing_form_essay_type,
        writing_form_task_type=writing_form_task_type,
        **common_context())


@app.get("/writing/clear")
@login_required
def clear_writing_topic():
    for key in [
        "generated_topic_text",
        "generated_topic_task",
        "generated_chart_data",
        "writing_result",
        "writing_result_data",
        "writing_mode",
        "inline_model_answer",
        "latest_model_answer",
        "writing_ideas_topic",
        "writing_ideas_question",
    ]:
        session.pop(key, None)
    target_mode = request.args.get("mode", "task1")
    flash("当前作文题目已清除，可以重新生成或手动输入。", "success")
    return redirect(url_for("writing", mode=target_mode))


@app.route("/analysis")
@login_required
def analysis():
    user_id = session["user_id"]
    tracked_profile = refresh_user_level_tracking(user_id)
    page = int_query("page", 1)
    type_filter = request.args.get("type", "").strip()
    all_progress = list(reversed(get_progress(user_id, limit=180)))
    auto_guidance = maybe_auto_refresh_learning_guidance(user_id, tracked_profile, all_progress)
    if auto_guidance.get("suggestions") or auto_guidance.get("study_plan"):
        all_progress = list(reversed(get_progress(user_id, limit=180)))
    study_plan_record = get_latest_progress_by_activity(user_id, STUDY_PLAN_ACTIVITY)
    suggestion_record = get_latest_progress_by_activity(user_id, IMPROVEMENT_SUGGESTIONS_ACTIVITY)
    study_plan = latest_saved_study_plan([study_plan_record] if study_plan_record else [])
    suggestions = latest_saved_suggestions([suggestion_record] if suggestion_record else [])
    progress = prepare_progress(all_progress)
    study_plan = ensure_exam_daily_schedule(tracked_profile, study_plan, progress)
    guidance_overview = learning_guidance_overview(tracked_profile, progress, suggestions, study_plan)
    if type_filter:
        progress = [p for p in progress if _matches_type_filter(p, type_filter)]
    progress, page, total_pages, total_records = paginate_records(progress, page, 10)
    user_words = get_user_words(user_id)
    context = common_context()
    context["profile"] = tracked_profile
    context["skill_scores"] = skill_score_overview(context["profile"])
    context["exam_countdown"] = exam_countdown(tracked_profile)
    context["guidance_overview"] = guidance_overview
    context["auto_guidance"] = auto_guidance
    return render_template(
        "analysis.html",
        progress=progress,
        page=page,
        total_pages=total_pages,
        total_records=total_records,
        study_plan=study_plan,
        suggestions=suggestions,
        user_words=user_words,
        type_filter=type_filter,
        **context,
    )


@app.route("/vocabulary")
@login_required
def vocabulary():
    context = common_context()
    query = request.args.get("q", "").strip().lower()
    topic = request.args.get("topic", "")
    page = int_query("page", 1)
    per_page = 60
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
    filtered_count = len(words)
    daily_goal = clamp_int(context.get("profile", {}).get("daily_vocab_goal"), 30, 5, 300)
    remaining_count = max(0, len(IELTS_WORDS) - learned_count)
    days_to_finish = math.ceil(remaining_count / daily_goal) if remaining_count else 0
    finish_date = (date.today() + timedelta(days=max(days_to_finish - 1, 0))).strftime("%Y-%m-%d") if days_to_finish else "已完成"
    total_pages = max(1, math.ceil(filtered_count / per_page))
    page = max(1, min(page, total_pages))
    def has_chinese_meaning(item):
        return bool(re.search(r"[\u4e00-\u9fff]", str(item.get("meaning", ""))))

    def needs_vocab_enrichment(item):
        phrases = item.get("phrases") or []
        generic_phrase = any(" in context" in str(phrase) or "IELTS writing" in str(phrase) for phrase in phrases)
        return (
            not has_chinese_meaning(item)
            or not item.get("phonetic")
            or item.get("topic") in {"雅思核心词", "通用学术词", "雅思中文词表"}
            or generic_phrase
        )

    page_words = []
    for item in words[(page - 1) * per_page:page * per_page]:
        display_item = dict(item)
        display_item["has_chinese_meaning"] = has_chinese_meaning(item)
        display_item["needs_enrichment"] = needs_vocab_enrichment(item)
        page_words.append(display_item)
    lookup_result = None
    if query and filtered_count == 0 and re.fullmatch(r"[A-Za-z][A-Za-z\-']{1,39}", query):
        lookup_result = lookup_word_locally(query)
        assistant, _ = current_assistant()
        if assistant is not None:
            try:
                raw = assistant.explain_word(query)
                parsed = parse_model_output(raw)
                enrichment = _parse_vocab_enrichment(parsed)
                lookup_result.update({
                    "translation": enrichment.get("meaning") or lookup_result["translation"],
                    "phrases": enrichment.get("phrases") or lookup_result["phrases"],
                    "usage": enrichment.get("essay_use") or lookup_result["usage"],
                    "phonetic": enrichment.get("phonetic", ""),
                    "topic": enrichment.get("topic", ""),
                    "source": "AI 查询",
                })
            except Exception:
                lookup_result["source"] = "临时查询"
    return render_template(
        "vocabulary.html",
        words=page_words,
        topics=topics,
        progress=progress,
        learned_count=learned_count,
        total_count=len(IELTS_WORDS),
        filtered_count=filtered_count,
        daily_goal=daily_goal,
        remaining_count=remaining_count,
        days_to_finish=days_to_finish,
        finish_date=finish_date,
        page=page,
        total_pages=total_pages,
        page_items=pagination_window(page, total_pages),
        user_words=user_words,
        selected_topic=topic,
        query=query,
        lookup_result=lookup_result,
        **context,
    )


@app.route("/vocabulary/review")
@login_required
def vocabulary_review():
    context = common_context()
    query = request.args.get("q", "").strip().lower()
    topic = request.args.get("topic", "")
    start = max(0, int_query("start", 0))
    deck_size = clamp_int(request.args.get("count"), context.get("profile", {}).get("daily_vocab_goal", 30), 5, 300)
    progress = get_vocab_progress(session["user_id"])
    words = IELTS_WORDS
    if query:
        words = [
            item for item in words
            if query in item["word"].lower() or query in item["meaning"].lower()
        ]
    if topic:
        words = [item for item in words if item["topic"] == topic]
    def has_chinese_meaning(item):
        return bool(re.search(r"[\u4e00-\u9fff]", str(item.get("meaning", ""))))

    def needs_vocab_enrichment(item):
        phrases = item.get("phrases") or []
        generic_phrase = any(" in context" in str(phrase) or "IELTS writing" in str(phrase) for phrase in phrases)
        return (
            not has_chinese_meaning(item)
            or not item.get("phonetic")
            or item.get("topic") in {"雅思核心词", "通用学术词", "雅思中文词表"}
            or generic_phrase
        )

    learning_words = [item for item in words if progress.get(item["word"], {}).get("status") != "learned"]
    learned_words = [item for item in words if progress.get(item["word"], {}).get("status") == "learned"]
    random.shuffle(learning_words)
    random.shuffle(learned_words)
    ordered_words = sorted(learning_words + learned_words, key=lambda item: not has_chinese_meaning(item))
    if start >= len(ordered_words):
        start = 0
    deck_words = ordered_words[start:start + deck_size]
    if not deck_words and ordered_words:
        deck_words = ordered_words[:deck_size]
        start = 0
    next_start = start + deck_size if start + deck_size < len(ordered_words) else 0
    prev_start = max(0, start - deck_size)
    learned_total = sum(1 for item in words if progress.get(item["word"], {}).get("status") == "learned")
    remaining_total = max(0, len(words) - learned_total)
    days_to_finish = math.ceil(remaining_total / deck_size) if remaining_total else 0
    finish_date = (date.today() + timedelta(days=max(days_to_finish - 1, 0))).strftime("%Y-%m-%d") if days_to_finish else "已完成"
    deck = [
        {
            "word": item.get("word", ""),
            "phonetic": item.get("phonetic", ""),
            "meaning": item.get("meaning", ""),
            "phrases": item.get("phrases", []),
            "essay_use": item.get("essay_use", ""),
            "topic": item.get("topic", ""),
            "learned": progress.get(item["word"], {}).get("status") == "learned",
            "needs_enrichment": needs_vocab_enrichment(item),
        }
        for item in deck_words
    ]
    return render_template(
        "vocabulary_review.html",
        deck=deck,
        query=query,
        selected_topic=topic,
        total_count=len(words),
        learned_count=learned_total,
        daily_goal=deck_size,
        start=start,
        next_start=next_start,
        prev_start=prev_start,
        remaining_count=remaining_total,
        days_to_finish=days_to_finish,
        finish_date=finish_date,
        **context,
    )


def _vocab_override_path():
    return os.path.join(os.path.dirname(__file__), "data", "vocab_ai_overrides.json")


def _save_vocab_ai_override(word, enrichment):
    os.makedirs(os.path.dirname(_vocab_override_path()), exist_ok=True)
    try:
        with open(_vocab_override_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data[word.lower()] = enrichment
    with open(_vocab_override_path(), "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    for item in IELTS_WORDS:
        if item.get("word", "").lower() == word.lower():
            item.update({key: value for key, value in enrichment.items() if value not in (None, "", [])})
            item["ai_enriched"] = True
            break


def _has_chinese_meaning(item):
    return bool(re.search(r"[\u4e00-\u9fff]", str(item.get("meaning", ""))))


def _needs_vocab_enrichment(item):
    phrases = item.get("phrases") or []
    generic_phrase = any(
        " in context" in str(phrase) or "IELTS writing" in str(phrase)
        for phrase in phrases
    )
    return (
        not _has_chinese_meaning(item)
        or not item.get("phonetic")
        or item.get("topic") in {"雅思核心词", "通用学术词", "雅思中文词表"}
        or generic_phrase
    )


def _parse_vocab_enrichment(raw_data):
    if not isinstance(raw_data, dict):
        raise ValueError("AI 返回格式无法解析。")
    meaning = raw_data.get("translation") or raw_data.get("meaning") or raw_data.get("中文释义") or ""
    phonetic = raw_data.get("phonetic") or raw_data.get("音标") or ""
    topic = raw_data.get("topic") or raw_data.get("话题") or ""
    phrases = raw_data.get("phrases") or raw_data.get("搭配") or []
    essay_use = raw_data.get("usage") or raw_data.get("essay_use") or raw_data.get("作文例句") or ""
    if isinstance(phrases, str):
        phrases = [phrases]
    enrichment = {
        "meaning": str(meaning).strip(),
        "phonetic": str(phonetic).strip(),
        "topic": str(topic).strip(),
        "phrases": [str(item).strip() for item in phrases if str(item).strip()][:6],
        "essay_use": str(essay_use).strip(),
    }
    if not enrichment["meaning"]:
        raise ValueError("AI 没有返回中文释义，请稍后重试。")
    return enrichment


def _enrich_vocab_item(assistant, target):
    raw = assistant.explain_word(target.get("word", ""))
    data = parse_model_output(raw)
    enrichment = _parse_vocab_enrichment(data)
    _save_vocab_ai_override(target.get("word", ""), enrichment)
    return enrichment


@app.post("/vocabulary/<word>/enrich")
@login_required
def vocabulary_enrich(word):
    assistant, _ = current_assistant()
    if assistant is None:
        return jsonify({"ok": False, "error": "请先在用户中心保存可用的 AI API Key。"}), 400
    target = next((item for item in IELTS_WORDS if item.get("word", "").lower() == word.lower()), None)
    if not target:
        return jsonify({"ok": False, "error": "词库中未找到这个单词。"}), 404
    try:
        enrichment = _enrich_vocab_item(assistant, target)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"AI 查词失败：{exc}"}), 500
    return jsonify({"ok": True, "word": target.get("word", word), **enrichment})


@app.post("/vocabulary/<word>/progress")
@login_required
def vocabulary_progress(word):
    status = request.form.get("status", "learned")
    save_vocab_progress(session["user_id"], word, status)
    if request.headers.get("X-Requested-With") == "fetch":
        progress = get_vocab_progress(session["user_id"])
        learned_count = sum(1 for item in IELTS_WORDS if progress.get(item["word"], {}).get("status") == "learned")
        return jsonify({"ok": True, "word": word, "status": status, "learned_count": learned_count, "total_count": len(IELTS_WORDS)})
    flash(f"{word} 已标记为{ '已掌握' if status == 'learned' else '学习中' }。", "success")
    return redirect(request.form.get("next") or url_for("vocabulary"))


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
            parsed = parse_model_output(raw)
            enrichment = _parse_vocab_enrichment(parsed)
            local.update({
                "translation": enrichment.get("meaning", local["translation"]),
                "phrases": enrichment.get("phrases", local["phrases"]),
                "usage": enrichment.get("essay_use", local["usage"]),
                "phonetic": enrichment.get("phonetic", ""),
                "topic": enrichment.get("topic", ""),
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
