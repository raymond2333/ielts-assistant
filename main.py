import streamlit as st
import json
import pandas as pd
from datetime import datetime
import os
import time
import hmac
import hashlib
import random
import uuid
from urllib.parse import urlsplit, urlunsplit
import ipaddress
from agents import TongyiIELTSAssistant
from utils import (
    authenticate_user,
    build_task1_chart_assets,
    create_progress_chart_data,
    create_score_gauge,
    cross_login_token,
    get_database_status,
    get_user_progress,
    initialize_database,
    learning_record_title,
    load_user_ai_config,
    load_user_api_key,
    load_user_profile,
    parse_generated_topic_md,
    parse_json_response,
    register_user,
    save_user_ai_config,
    save_user_api_key,
    save_user_profile,
    save_user_progress,
    validate_essay_length,
    verify_cross_token,
)
import re
from typing import Dict, Any, List


os.environ.setdefault("MYSQL_ENABLED", "true")
os.environ.setdefault("MYSQL_HOST", "127.0.0.1")
os.environ.setdefault("MYSQL_PORT", "3307")
os.environ.setdefault("MYSQL_USER", "ielts")
os.environ.setdefault("MYSQL_PASSWORD", "ielts")
os.environ.setdefault("MYSQL_DATABASE", "ielts_learning")

SHARED_SECRET = os.getenv("FLASK_SECRET_KEY", "ielts-dev-secret-key")
LAST_USER_FILE = os.path.join(os.path.expanduser("~"), ".ielts_last_user.json")


def _save_last_user(user_id):
    try:
        with open(LAST_USER_FILE, "w") as f:
            json.dump({"last_user_id": user_id}, f)
    except Exception:
        pass


def _load_last_user():
    try:
        if os.path.exists(LAST_USER_FILE):
            with open(LAST_USER_FILE, "r") as f:
                data = json.load(f)
                return data.get("last_user_id", "")
    except Exception:
        pass
    return ""


def _cross_login_token(user_id):
    return cross_login_token(user_id)


def _normalize_base_url(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    return f"http://{value}"


def _replace_url_port(base_url: str, port: str) -> str:
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


def _streamlit_request_base_url() -> str:
    context = getattr(st, "context", None)
    if context is not None:
        url = getattr(context, "url", "") or ""
        if url:
            parts = urlsplit(url)
            if parts.scheme and parts.netloc:
                return urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")
        headers = getattr(context, "headers", None)
        if headers:
            try:
                host = headers.get("X-Forwarded-Host") or headers.get("Host") or headers.get("host")
                proto = headers.get("X-Forwarded-Proto") or "http"
                if host:
                    return f"{str(proto).split(',')[0].strip()}://{str(host).split(',')[0].strip()}".rstrip("/")
            except Exception:
                pass
    return ""


def _is_private_host(hostname: str) -> bool:
    try:
        ip = ipaddress.ip_address((hostname or "").strip("[]"))
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


def _should_ignore_private_env_host(env_url: str) -> bool:
    env_host = urlsplit(_normalize_base_url(env_url)).hostname or ""
    current = _streamlit_request_base_url()
    current_host = urlsplit(current).hostname if current else ""
    return _is_private_host(env_host) and current_host and not _is_private_host(current_host)


def _flask_base_url():
    explicit = _normalize_base_url(os.getenv("NEW_FLASK_URL", ""))
    if explicit and not _should_ignore_private_env_host(explicit):
        return explicit
    domain = _normalize_base_url(os.getenv("SERVER_DOMAIN", ""))
    flask_port = os.getenv("WEB_PORT", "8600")
    if domain and not _should_ignore_private_env_host(domain):
        return _replace_url_port(domain, flask_port)
    current = _streamlit_request_base_url()
    if current:
        return _replace_url_port(current, flask_port)
    return f"http://127.0.0.1:{flask_port}"


def _verify_cross_token(user_id, token):
    return verify_cross_token(user_id, token)


def _extract_part2_topic_for_discussion(question_data: Dict[str, Any]) -> str:
    """从Part 2题目卡中提取Part 3可承接讨论的话题。"""
    if not isinstance(question_data, dict):
        return ""

    cue_card = question_data.get("cue_card", "")
    if isinstance(cue_card, str) and cue_card.strip():
        describe_match = re.search(r"\*\*Describe\s+(.+?)\*\*", cue_card, re.IGNORECASE | re.DOTALL)
        if describe_match:
            return describe_match.group(1).strip()
        return cue_card.strip()

    if isinstance(cue_card, dict):
        return cue_card.get("topic") or cue_card.get("prompt") or ""

    return question_data.get("topic") or question_data.get("prompt") or ""


def _profile_overall_level(profile: Dict[str, Any]) -> float:
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


AI_PROVIDERS = {
    "tongyi": {
        "label": "通义千问 Dashscope",
        "default_model": "qwen-turbo",
        "base_url": "",
        "env_key": "DASHSCOPE_API_KEY",
    },
    "deepseek": {
        "label": "DeepSeek",
        "default_model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "env_key": "DEEPSEEK_API_KEY",
    },
    "openai": {
        "label": "OpenAI",
        "default_model": "gpt-4o-mini",
        "base_url": "",
        "env_key": "OPENAI_API_KEY",
    },
    "custom": {
        "label": "OpenAI兼容接口",
        "default_model": "gpt-4o-mini",
        "base_url": "",
        "env_key": "",
    },
}


def _provider_label(provider: str) -> str:
    return AI_PROVIDERS.get(provider, AI_PROVIDERS["tongyi"])["label"]


def _provider_from_label(label: str) -> str:
    for provider, config in AI_PROVIDERS.items():
        if config["label"] == label:
            return provider
    return "tongyi"


# 页面设置
st.set_page_config(
    page_title="信达雅",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 口语Part 1界面函数
def _render_speaking_part1():
    st.write("**Part 1: 自我介绍与日常话题**")

    col1, col2 = st.columns(2)

    with col1:
        topic = st.selectbox(
            "选择话题类型",
            ["工作/学习", "家乡", "家庭", "兴趣爱好", "日常生活", "旅行", "食物", "节日"]
        )

        difficulty = st.select_slider(
            "难度级别",
            options=["简单", "中等", "困难"]
        )

        # 添加刷新按钮，确保状态正确维护
        if 'refresh_trigger' not in st.session_state:
            st.session_state.refresh_trigger = 0
            
        if st.button("生成Part 1题目", type="primary"):
            with st.spinner("正在生成Part 1题目..."):
                try:
                    result = st.session_state.tongyi_agent.practice_speaking_part1(
                        topic=topic,
                        difficulty=difficulty
                    )
                    parsed_result = parse_json_response(result)
                    
                    # 验证结果格式
                    if isinstance(parsed_result, dict) and "questions" in parsed_result:
                        st.session_state.current_speaking_question = parsed_result
                        st.session_state.question_generated = True
                        st.session_state.refresh_trigger += 1  # 触发刷新
                        save_user_progress(
                            st.session_state.user_profile.get("user_id", "default_user"),
                            "口语Part 1题目生成",
                            {
                                "mode": "part1",
                                "topic": topic,
                                "difficulty": difficulty,
                                "result_data": parsed_result,
                                "timestamp": datetime.now().isoformat(),
                            },
                        )
                        st.success("Part 1题目生成成功！请查看下方题目列表")
                    else:
                        st.error("生成的题目格式不正确，请重试")
                        st.session_state.question_generated = False
                except Exception as e:
                    st.error(f"生成题目时出错: {str(e)}")
                    st.session_state.question_generated = False

    with col2:
        st.write("**Part 1特点：**")
        st.write("""
        - 4-5分钟时长
        - 3个话题领域
        - 每个话题3-4个问题
        - 考察日常交流能力
        - 重点：流利度、自然度
        """)

    # 显示题目和回答 - 确保状态变量正确检查
    if "current_speaking_question" in st.session_state and \
       "question_generated" in st.session_state and \
       st.session_state.question_generated and \
       isinstance(st.session_state.current_speaking_question, dict):
        
        question_data = st.session_state.current_speaking_question
        
        # 确保有questions字段并且是列表格式
        if "questions" in question_data and isinstance(question_data["questions"], list):
            st.markdown("---")
            st.subheader("📋 练习题目")

            for i, q in enumerate(question_data["questions"]):
                with st.expander(f"问题 {i + 1}: {q.get('question', '')}"):
                    if "keywords" in q:
                        with st.expander("🔑 关键词提示"):
                            st.write(", ".join(q["keywords"]))
                    if "tips" in q:
                        with st.expander("💡 回答技巧"):
                            for tip in q["tips"]:
                                st.markdown(f"- {tip}")

                    if "model_answer" in q:
                        with st.expander("📖 参考答案"):
                            st.write(q["model_answer"])

                    # 用户回答区域
                    user_response = st.text_area(
                        f"你的回答 {i + 1}",
                        placeholder="在这里输入你的回答...",
                        key=f"part1_response_{i}"
                    )

                    feedback_key = f"part1_feedback_result_{i}"
                    if user_response and st.button(f"获取反馈 {i + 1}", key=f"feedback_{i}"):
                        with st.spinner("正在分析你的回答..."):
                            try:
                                feedback = st.session_state.tongyi_agent.get_speaking_feedback_direct(
                                    question=q["question"],
                                    user_response=user_response,
                                    target_score=st.session_state.user_profile["target_score"]
                                )
                                feedback_data = parse_json_response(feedback)
                                st.session_state[feedback_key] = feedback_data
                            except Exception as e:
                                st.error(f"获取反馈时出错: {str(e)}")

                    if feedback_key in st.session_state and st.session_state[feedback_key]:
                        _display_speaking_feedback(st.session_state[feedback_key])

                    with st.expander("🔑 根据关键词生成完整答案"):
                        keyword_input = st.text_area(
                            f"关键词 {i + 1}",
                            placeholder="例如：weekends, coffee shop, relax, friends",
                            key=f"part1_keywords_{i}"
                        )
                        answer_key = f"part1_keyword_answer_{i}"
                        if keyword_input and st.button(f"生成完整答案 {i + 1}", key=f"part1_keyword_btn_{i}"):
                            with st.spinner("正在根据关键词生成答案..."):
                                result = st.session_state.tongyi_agent.generate_answer_from_keywords(
                                    question=q["question"],
                                    keywords=keyword_input,
                                    part="Part 1"
                                )
                                st.session_state[answer_key] = parse_json_response(result)
                                save_user_progress(
                                    st.session_state.user_profile.get("user_id", "default_user"),
                                    "关键词生成答案",
                                    {
                                        "mode": "keyword_answer",
                                        "question": q["question"],
                                        "keywords": keyword_input,
                                        "result": result,
                                        "result_data": st.session_state[answer_key],
                                        "timestamp": datetime.now().isoformat(),
                                    },
                                )
                        if answer_key in st.session_state:
                            _display_record_result_data(st.session_state[answer_key])


# 口语Part 2界面函数
def _render_speaking_part2():
    st.write("**Part 2: 个人陈述**")

    col1, col2 = st.columns(2)

    with col1:
        topic = st.selectbox(
            "选择话题卡类型",
            ["人物描述", "地点描述", "事件经历", "物品描述", "活动经历", "理想目标"]
        )

        cue_card_type = st.selectbox(
            "题目卡类型",
            ["描述类", "经历类", "观点类", "比较类"]
        )

        # 使用session_state来管理生成状态，避免刷新后消失
        if st.button("生成Part 2题目卡", type="primary"):
            with st.spinner("正在生成Part 2题目卡..."):
                try:
                    result = st.session_state.tongyi_agent.practice_speaking_part2(
                        topic=topic,
                        cue_card_type=cue_card_type
                    )
                    # Part 2 输出是 Markdown 格式，直接存储原始结果
                    parsed_result = parse_json_response(result)
                    
                    # 检查是否是 JSON 格式（结构化数据）还是 Markdown 格式
                    if isinstance(parsed_result, dict) and "answer" in parsed_result and len(parsed_result) == 1:
                        # 这是 Markdown 格式输出，直接使用原始文本
                        st.session_state.current_speaking_question = {
                            "cue_card": result,
                            "raw_response": result
                        }
                    elif isinstance(parsed_result, dict):
                        st.session_state.current_speaking_question = parsed_result
                    else:
                        st.session_state.current_speaking_question = {
                            "cue_card": result,
                            "raw_response": result
                        }
                    
                    st.session_state.latest_part2_question = st.session_state.current_speaking_question
                    st.session_state.latest_part2_topic = _extract_part2_topic_for_discussion(st.session_state.current_speaking_question)
                    st.session_state.question_generated = True
                    st.session_state.showing_answer = False  # 重置答案显示状态
                    
                    # 确保refresh_trigger存在
                    if 'refresh_trigger' not in st.session_state:
                        st.session_state.refresh_trigger = 0
                    st.session_state.refresh_trigger += 1  # 触发刷新
                    save_user_progress(
                        st.session_state.user_profile.get("user_id", "default_user"),
                        "口语Part 2题目生成",
                        {
                            "mode": "part2",
                            "topic": topic,
                            "cue_type": cue_card_type,
                            "result_data": st.session_state.current_speaking_question,
                            "timestamp": datetime.now().isoformat(),
                        },
                    )
                    
                    st.success("题目卡生成成功！请查看下方题目卡")

                except Exception as e:
                    st.error(f"生成题目卡时出错: {str(e)}")
                    st.session_state.question_generated = False

    with col2:
        st.write("**Part 2特点：**")
        st.write("""
        - 准备时间：1分钟
        - 发言时间：2分钟
        - 题目卡引导
        - 考察连贯叙述能力
        - 重点：内容组织、词汇丰富度
        """)

        st.write("**备考技巧：**")
        st.write("""
        1. 利用1分钟准备时间做笔记
        2. 按照题目卡要点组织内容
        3. 使用时间顺序或逻辑顺序
        4. 加入具体细节和例子
        5. 注意时间控制
        """)

    # 显示题目卡 - 使用新的状态管理变量
    if "current_speaking_question" in st.session_state and "question_generated" in st.session_state and st.session_state.question_generated:
        question_data = st.session_state.current_speaking_question

        if "cue_card" in question_data or "topic" in question_data:  # 增加兼容性，支持不同格式的数据
            st.markdown("---")
            st.subheader("🎯 题目卡")

            # 处理不同格式的数据结构
            if "cue_card" in question_data:
                card = question_data["cue_card"]
                if isinstance(card, str):
                    # 新格式：直接显示Markdown格式的cue_card
                    st.markdown(card)
                else:
                    # 兼容旧格式
                    st.info(f"""
                    **话题:** {card.get('topic', '')}
                    **提示:** {card.get('prompt', '')}
                    **时间:** {card.get('time', '1分钟准备，2分钟发言')}
                    """)
            else:
                # 直接从question_data中获取信息
                st.info(f"""
                **话题:** {question_data.get('topic', '')}
                **提示:** {question_data.get('prompt', '')}
                **时间:** {question_data.get('time', '1分钟准备，2分钟发言')}
                """)

            # 计时器功能
            col1, col2, col3 = st.columns(3)
            
            # 倒计时显示占位符
            timer_placeholder = st.empty()
            
            with col1:
                if st.button("⏱️ 开始1分钟准备", key="prepare_timer_btn"):
                    st.session_state.timer_active = True
                    st.session_state.timer_type = "prepare"
                    st.session_state.remaining_time = 60  # 1分钟
                    st.warning("准备时间开始！请快速构思并做笔记")
                    
                    # 倒计时循环
                    while st.session_state.remaining_time > 0 and st.session_state.timer_active:
                        mins, secs = divmod(st.session_state.remaining_time, 60)
                        timer_placeholder.metric("⏱️ 准备倒计时", f"{mins:02d}:{secs:02d}")
                        time.sleep(1)
                        st.session_state.remaining_time -= 1
                    
                    # 时间结束提醒
                    if st.session_state.remaining_time == 0 and not st.session_state.timer_active:
                        timer_placeholder.error("⏱️ 准备时间结束！请开始发言")
            
            with col2:
                if st.button("🎤 开始2分钟发言", key="speak_timer_btn"):
                    st.session_state.timer_active = True
                    st.session_state.timer_type = "speak"
                    st.session_state.remaining_time = 120  # 2分钟
                    st.success("发言时间开始！请连贯地表达")
                    
                    # 倒计时循环
                    while st.session_state.remaining_time > 0 and st.session_state.timer_active:
                        mins, secs = divmod(st.session_state.remaining_time, 60)
                        timer_placeholder.metric("⏱️ 发言倒计时", f"{mins:02d}:{secs:02d}")
                        time.sleep(1)
                        st.session_state.remaining_time -= 1
                    
                    # 时间结束提醒
                    if st.session_state.remaining_time == 0 and not st.session_state.timer_active:
                        timer_placeholder.error("⏱️ 发言时间结束！")
            
            with col3:
                if st.button("⏹️ 停止计时", key="stop_timer_btn"):
                    st.session_state.timer_active = False
                    st.session_state.remaining_time = 0
                    timer_placeholder.info("⏱️ 计时器已停止")
            
            # 显示当前计时器状态（如果页面刷新）
            if st.session_state.timer_active:
                mins, secs = divmod(st.session_state.remaining_time, 60)
                timer_type_text = "准备" if st.session_state.timer_type == "prepare" else "发言"
                timer_placeholder.metric(f"⏱️ {timer_type_text}倒计时", f"{mins:02d}:{secs:02d}")
                # 添加刷新提示
                with col3:
                    st.info("提示：计时器运行时请勿刷新页面")

            # 用户回答区域
            user_response = st.text_area(
                "你的个人陈述",
                placeholder="在这里输入你的2分钟发言内容...",
                height=200
            )

            if user_response and st.button("获取专业反馈"):
                with st.spinner("正在详细分析你的回答..."):
                    try:
                        question_text = ""
                        if isinstance(card, str):
                            question_text = card
                        else:
                            question_text = card.get('prompt', '')

                        feedback = st.session_state.tongyi_agent.get_speaking_feedback_direct(
                                question=question_text,
                                user_response=user_response,
                                target_score=st.session_state.user_profile["target_score"]
                            )
                        feedback_data = parse_json_response(feedback)
                        st.session_state.part2_feedback_result = feedback_data
                    except Exception as e:
                        st.error(f"获取反馈时出错: {str(e)}")

            if "part2_feedback_result" in st.session_state and st.session_state.part2_feedback_result:
                _display_speaking_feedback(st.session_state.part2_feedback_result)

            # 关键词生成完整答案
            st.markdown("---")
            st.subheader("🔑 根据关键词生成完整答案")
            st.caption("输入你准备的关键词，AI 将围绕这些关键词为你生成一个自然流利的完整答案。")
            keywords_input = st.text_area(
                "你的关键词",
                placeholder="输入你想用的关键词，每行一个或用逗号分隔\n例如：\nchildhood memory, river, fishing, grandfather, patient, life lesson",
                height=100,
                key="part2_keywords"
            )
            if keywords_input and st.button("✨ 生成完整答案", key="gen_keyword_answer"):
                with st.spinner("正在根据关键词生成完整答案..."):
                    try:
                        question_text = ""
                        if isinstance(card, str):
                            question_text = card
                        else:
                            question_text = card.get('prompt', '')
                        result = st.session_state.tongyi_agent.generate_answer_from_keywords(
                            question=question_text,
                            keywords=keywords_input,
                            part="Part 2"
                        )
                        st.session_state.part2_keyword_answer = parse_json_response(result)
                    except Exception as e:
                        st.error(f"生成答案时出错: {str(e)}")

            if "part2_keyword_answer" in st.session_state and st.session_state.part2_keyword_answer:
                kw_data = st.session_state.part2_keyword_answer
                with st.expander("✨ 基于关键词生成的完整答案", expanded=True):
                    if "full_answer" in kw_data:
                        st.write("**完整答案：**")
                        st.write(kw_data["full_answer"])
                    if "answer_structure" in kw_data:
                        st.write("**答案结构：**", kw_data["answer_structure"])
                    if "advanced_vocabulary" in kw_data:
                        st.write("**高级词汇：**")
                        vocab_cols = st.columns(3)
                        for i, w in enumerate(kw_data["advanced_vocabulary"]):
                            vocab_cols[i % 3].code(w)
                    if "useful_phrases" in kw_data:
                        st.write("**实用短语：**")
                        phrase_cols = st.columns(3)
                        for i, p in enumerate(kw_data["useful_phrases"]):
                            phrase_cols[i % 3].code(p)
                    if "improvement_tips" in kw_data:
                        st.write("**改进建议：**", kw_data["improvement_tips"])

            if "model_answer" in question_data:
                with st.expander("🌟 高分参考答案"):
                    model = question_data["model_answer"]
                    if isinstance(model, str):
                        st.write(model)
                    else:
                        answer_parts = []
                        if "introduction" in model:
                            st.write("**开头介绍:**")
                            st.write(model["introduction"])
                            answer_parts.append(str(model["introduction"]))
                        if "main_points" in model:
                            st.write("**主要要点:**")
                            for point in model["main_points"]:
                                st.write(f"• {point}")
                            answer_parts.extend(str(point) for point in model["main_points"])
                        if "details" in model:
                            st.write("**详细描述:**")
                            for detail in model["details"]:
                                st.write(f"• {detail}")
                            answer_parts.extend(str(detail) for detail in model["details"])
                        if "conclusion" in model:
                            st.write("**结尾:**")
                            st.write(model["conclusion"])
                            answer_parts.append(str(model["conclusion"]))

# 口语Part 3界面函数
def _render_speaking_part3():
    st.write("**Part 3: 深入讨论**")

    st.info("💡 Part 3基于Part 2的话题进行深入讨论，考察分析能力和批判性思维")

    topic_mode = st.radio(
        "话题来源",
        ["沿用AI生成的Part 2话题", "手动输入讨论话题"],
        horizontal=True,
        key="part3_topic_mode"
    )

    latest_part2_topic = st.session_state.get("latest_part2_topic", "")
    if topic_mode == "沿用AI生成的Part 2话题":
        if latest_part2_topic:
            part2_topic = latest_part2_topic
            st.text_area(
                "当前沿用的Part 2话题",
                value=part2_topic,
                height=140,
                disabled=True,
                help="该内容来自最近一次AI生成的Part 2题目卡"
            )
        else:
            part2_topic = ""
            st.warning("还没有可沿用的AI生成Part 2话题。请先到Part 2生成题目卡，或切换为手动输入模式。")
    else:
        part2_topic = st.text_area(
            "想深入讨论的话题",
            placeholder="输入你希望Part 3围绕讨论的话题，例如：a memorable journey, environmental protection, online education...",
            height=120,
            help="系统会基于这个话题生成Part 3深入讨论题"
        ).strip()

    discussion_type = st.selectbox(
        "讨论类型",
        ["社会影响", "发展趋势", "比较分析", "问题解决", "个人观点"]
    )

    if st.button("生成Part 3讨论题", type="primary") and part2_topic:
        with st.spinner("正在生成深入的讨论题目..."):
            try:
                result = st.session_state.tongyi_agent.practice_speaking_part3(
                    part2_topic=part2_topic,
                    discussion_type=discussion_type
                )
                parsed_result = parse_json_response(result)
                
                # 验证结果格式
                if isinstance(parsed_result, dict) and "discussion_questions" in parsed_result:
                    st.session_state.current_part3_question = parsed_result
                    st.session_state.current_part3_topic = part2_topic
                    st.session_state.part3_question_generated = True
                    
                    # 确保refresh_trigger存在
                    if 'refresh_trigger' not in st.session_state:
                        st.session_state.refresh_trigger = 0
                    st.session_state.refresh_trigger += 1  # 触发刷新
                    save_user_progress(
                        st.session_state.user_profile.get("user_id", "default_user"),
                        "口语Part 3题目生成",
                        {
                            "mode": "part3",
                            "topic": part2_topic,
                            "discussion_type": discussion_type,
                            "result_data": parsed_result,
                            "timestamp": datetime.now().isoformat(),
                        },
                    )
                    
                    st.success("Part 3讨论题生成成功！请查看下方讨论题目")
                else:
                    st.error("生成的讨论题格式不正确，请重试")
                    st.session_state.part3_question_generated = False
            except Exception as e:
                st.error(f"生成讨论题时出错: {str(e)}")
                st.session_state.part3_question_generated = False

    # 显示讨论题目 - 确保状态变量和数据格式正确检查
    if "current_part3_question" in st.session_state and \
       "part3_question_generated" in st.session_state and \
       st.session_state.part3_question_generated and \
       isinstance(st.session_state.current_part3_question, dict):
        
        question_data = st.session_state.current_part3_question

        # 确保有discussion_questions字段并且是列表格式
        if "discussion_questions" in question_data and isinstance(question_data["discussion_questions"], list):
            st.markdown("---")
            st.subheader("💭 讨论题目")
            if st.session_state.get("current_part3_topic"):
                st.caption(f"基于话题：{st.session_state.current_part3_topic}")

            for i, q in enumerate(question_data["discussion_questions"]):
                with st.expander(f"讨论题 {i + 1}: {q.get('question', '')}"):
                    if "purpose" in q:
                        st.write(f"**考察目的:** {q['purpose']}")

                    # 添加参考答案按钮
                    if "model_response" in q:
                        with st.expander("🌟 高分参考答案"):
                            st.write(q["model_response"])

                    if "depth_required" in q:
                        st.write(f"**要求深度:** {q['depth_required']}")

                    # 用户回答区域
                    user_response = st.text_area(
                        f"你的观点 {i + 1}",
                        placeholder="在这里输入你的分析和观点...",
                        key=f"part3_response_{i}"
                    )

                    if user_response and st.button(f"分析回答 {i + 1}", key=f"part3_feedback_{i}"):
                        with st.spinner("正在分析你的讨论回答..."):
                            try:
                                feedback = st.session_state.tongyi_agent.get_speaking_feedback_direct(
                                    question=q["question"],
                                    user_response=user_response,
                                    target_score=st.session_state.user_profile["target_score"]
                                )
                                feedback_data = parse_json_response(feedback)
                                st.session_state[f"part3_feedback_result_{i}"] = feedback_data
                            except Exception as e:
                                st.error(f"分析回答时出错: {str(e)}")

                    fb_key = f"part3_feedback_result_{i}"
                    if fb_key in st.session_state and st.session_state[fb_key]:
                        _display_speaking_feedback(st.session_state[fb_key])

                    with st.expander("🔑 根据关键词生成完整答案"):
                        keyword_input = st.text_area(
                            f"关键词 {i + 1}",
                            placeholder="例如：technology, communication, efficiency, drawbacks",
                            key=f"part3_keywords_{i}"
                        )
                        answer_key = f"part3_keyword_answer_{i}"
                        if keyword_input and st.button(f"生成完整答案 {i + 1}", key=f"part3_keyword_btn_{i}"):
                            with st.spinner("正在根据关键词生成答案..."):
                                result = st.session_state.tongyi_agent.generate_answer_from_keywords(
                                    question=q["question"],
                                    keywords=keyword_input,
                                    part="Part 3"
                                )
                                st.session_state[answer_key] = parse_json_response(result)
                                save_user_progress(
                                    st.session_state.user_profile.get("user_id", "default_user"),
                                    "关键词生成答案",
                                    {
                                        "mode": "keyword_answer",
                                        "question": q["question"],
                                        "keywords": keyword_input,
                                        "result": result,
                                        "result_data": st.session_state[answer_key],
                                        "timestamp": datetime.now().isoformat(),
                                    },
                                )
                        if answer_key in st.session_state:
                            _display_record_result_data(st.session_state[answer_key])


def _render_writing_task1():
    st.write("**Task 1: 小作文（图表描述）**")

    gen_col1, gen_col2 = st.columns([3, 1])
    with gen_col1:
        st.caption("点击生成随机小作文题目（含图表），题目将自动填入下方练习区")
    with gen_col2:
        if st.button("🎲 生成小作文题目", use_container_width=True, key="gen_task1"):
            with st.spinner("正在生成小作文题目..."):
                result = st.session_state.tongyi_agent.generate_writing_topic("Task 1")
                parsed = parse_generated_topic_md(result, "Task 1")
                if parsed and isinstance(parsed, dict):
                    parsed = build_task1_chart_assets(parsed, raw_text=result)
                    st.session_state.generated_writing_topic = parsed
                    st.session_state.imported_topic_question = parsed.get("question", "")
                    st.rerun()
                save_user_progress(
                    st.session_state.user_profile.get("user_id", "default_user"),
                    "生成作文题目",
                    {"mode": "generate_topic", "task_type": "Task 1", "result": result, "result_data": parsed, "timestamp": datetime.now().isoformat()},
                )

    # 显示生成的题目结果（含图表图片）
    gen = st.session_state.get("generated_writing_topic")
    if gen and gen.get("task_type") == "Task 1":
        if gen.get("chart_type"):
            st.markdown(f"**图表类型：** {gen['chart_type']}")
        if gen.get("chart_image"):
            st.image(os.path.join(os.path.dirname(__file__), gen["chart_image"]))
        if gen.get("question"):
            st.info(f"📌 **题目：** {gen['question']}")
        if gen.get("key_features"):
            with st.expander("关键特征", expanded=False):
                for f in gen["key_features"]:
                    st.markdown(f"- {f}")
        if gen.get("suggested_structure"):
            with st.expander("建议结构", expanded=False):
                st.write(gen["suggested_structure"])
        if gen.get("chart_data"):
            with st.expander("表格数据", expanded=False):
                st.dataframe(pd.DataFrame(gen["chart_data"]))

    # 显示导入的题目
    imported_q = st.session_state.get("imported_topic_question", None)
    if imported_q:
        st.info(f"📌 **已导入题目：**\n\n{imported_q}")

    col1, col2 = st.columns(2)

    with col1:
        task_type = st.selectbox(
            "图表类型",
            ["线形图", "柱状图", "饼图", "表格", "流程图", "地图"]
        )

        essay_content = st.text_area(
            "输入你的小作文",
            placeholder="在这里粘贴或输入你的Task 1作文..." + ("（题目已导入到上方）" if imported_q else ""),
            height=300,
            help="小作文建议字数：150-200字"
        )

        target_score = st.slider("目标分数", 5.0, 8.0, 6.5, 0.5, key="task1_target_score")

        if st.button("📊 批改小作文", type="primary") and essay_content:
            # 字数验证
            is_valid, word_msg = validate_essay_length(essay_content, 100, 250)
            if not is_valid:
                st.warning(word_msg)
            else:
                with st.spinner("正在详细批改你的小作文..."):
                    try:
                        result = st.session_state.tongyi_agent.correct_writing_task1(
                            task_type=task_type,
                            essay_content=essay_content,
                            target_score=target_score
                        )
                        st.session_state.current_writing_feedback = parse_json_response(result)
                    except Exception as e:
                        st.error(f"批改作文时出错: {str(e)}")

    with col2:
        st.write("**Task 1评分标准:**")
        st.write("""
        **任务完成度 (Task Achievement)**
        - 是否准确描述图表信息
        - 是否涵盖主要特征
        - 是否进行适当比较

        **连贯与衔接 (Coherence & Cohesion)**
        - 文章结构是否清晰
        - 逻辑顺序是否合理
        - 连接词使用是否恰当

        **词汇资源 (Lexical Resource)**
        - 词汇是否丰富准确
        - 是否使用图表描述专用词汇
        - 拼写是否正确

        **语法范围与准确性 (Grammatical Range & Accuracy)**
        - 句式是否多样
        - 语法是否正确
        - 时态使用是否恰当
        """)

        st.write("**写作技巧:**")
        st.write("""
        1. **开头段**: 重述题目，说明图表主题
        2. **概述段**: 总结主要趋势或特征
        3. **细节段**: 详细描述具体数据
        4. **使用**: 上升、下降、波动、稳定等词汇
        5. **注意**: 时态一致性、数据准确性
        """)

    # 显示批改结果
    if "current_writing_feedback" in st.session_state:
        feedback_data = st.session_state.current_writing_feedback
        _display_writing_feedback(feedback_data, "Task 1")


# 大作文批改界面函数
def _render_writing_task2():
    st.write("**Task 2: 大作文（议论文）**")

    gen_col1, gen_col2 = st.columns([3, 1])
    with gen_col1:
        st.caption("点击生成随机大作文题目，题目将自动填入下方练习区")
    with gen_col2:
        if st.button("🎲 生成大作文题目", use_container_width=True, key="gen_task2"):
            with st.spinner("正在生成大作文题目..."):
                result = st.session_state.tongyi_agent.generate_writing_topic("Task 2")
                parsed = parse_generated_topic_md(result, "Task 2")
                if parsed and isinstance(parsed, dict):
                    st.session_state.generated_writing_topic = parsed
                    st.session_state.imported_topic_question = parsed.get("question", "")
                    st.rerun()
                save_user_progress(
                    st.session_state.user_profile.get("user_id", "default_user"),
                    "生成作文题目",
                    {"mode": "generate_topic", "task_type": "Task 2", "result": result, "result_data": parsed, "timestamp": datetime.now().isoformat()},
                )

    # 显示生成的题目结果
    gen = st.session_state.get("generated_writing_topic")
    if gen and gen.get("task_type") == "Task 2":
        if gen.get("topic_category"):
            st.markdown(f"**话题类别：** {gen['topic_category']}")
        if gen.get("essay_type"):
            st.markdown(f"**作文类型：** {gen['essay_type']}")
        if gen.get("question"):
            st.info(f"📌 **题目：** {gen['question']}")
        if gen.get("key_points"):
            with st.expander("关键论点", expanded=False):
                for pt in gen["key_points"]:
                    st.markdown(f"- {pt}")
        if gen.get("suggested_structure"):
            with st.expander("建议结构", expanded=False):
                st.write(gen["suggested_structure"])

    # 显示导入的题目
    imported_q = st.session_state.get("imported_topic_question", None)
    if imported_q:
        st.info(f"📌 **已导入题目：**\n\n{imported_q}")

    col1, col2 = st.columns(2)

    with col1:
        # 大作文话题选择
        topic_category = st.selectbox(
            "话题类别",
            ["教育", "科技", "环境", "社会", "文化", "工作", "政府", "全球化"]
        )

        essay_type = st.selectbox(
            "作文类型",
            ["同意不同意型", "讨论双方观点型", "利弊分析型", "问题解决型"]
        )

        essay_content = st.text_area(
            "输入你的大作文",
            placeholder="在这里粘贴或输入你的Task 2作文...",
            height=300,
            help="大作文建议字数：250-300字"
        )

        target_score = st.slider("目标分数", 5.0, 8.0, 6.5, 0.5, key="task2_target_score")

        if st.button("📝 批改大作文", type="primary") and essay_content:
            # 字数验证
            is_valid, word_msg = validate_essay_length(essay_content, 200, 350)
            if not is_valid:
                st.warning(word_msg)
            else:
                with st.spinner("正在详细批改你的大作文..."):
                    try:
                        result = st.session_state.tongyi_agent.correct_writing_task2(
                            topic=topic_category,
                            essay_type=essay_type,
                            essay_content=essay_content,
                            target_score=target_score
                        )
                        st.session_state.current_writing_feedback = parse_json_response(result)
                    except Exception as e:
                        st.error(f"批改作文时出错: {str(e)}")

    with col2:
        st.write("**Task 2评分标准:**")
        st.write("""
        **任务回应 (Task Response)**
        - 是否直接回应题目
        - 立场是否清晰
        - 论证是否充分

        **连贯与衔接 (Coherence & Cohesion)**
        - 文章结构是否合理
        - 段落衔接是否自然
        - 逻辑推理是否清晰

        **词汇资源 (Lexical Resource)**
        - 词汇是否丰富准确
        - 是否使用学术词汇
        - 用词是否恰当

        **语法范围与准确性 (Grammatical Range & Accuracy)**
        - 句式结构是否多样
        - 复杂句使用是否恰当
        - 语法错误数量
        """)

        st.write("**写作结构建议:**")
        st.write("""
        **四段式结构:**
        1. **引言段**: 背景介绍 + 明确立场
        2. **主体段1**: 主要论点 + 论据支持
        3. **主体段2**: 另一角度或让步段
        4. **结论段**: 总结观点 + 建议展望
        """)

    # 显示批改结果
    if "current_writing_feedback" in st.session_state:
        feedback_data = st.session_state.current_writing_feedback
        _display_writing_feedback(feedback_data, "Task 2")


# 显示写作反馈的通用函数
def _display_writing_feedback(feedback_data, task_type):
    """增强版写作反馈显示函数，支持新的批改结果格式"""
    st.markdown("---")
    st.subheader(f"📊 {task_type} 批改结果")
    
    # 保存用户进度记录
    try:
        if "overall_score" in feedback_data:
            user_id = st.session_state.user_profile.get("user_id", "default_user")
            # 确保分数符合雅思格式
            score = float(feedback_data["overall_score"])
            # 将分数舍入为符合雅思标准的0.5分间隔格式
            formatted_score = round(score * 2) / 2
            save_user_progress(
                user_id=user_id,
                activity=f"写作 {task_type} 练习",
                data={
                    "score": formatted_score,
                    "task_type": task_type,
                    "timestamp": datetime.now().isoformat()
                }
            )
    except Exception as e:
        print(f"保存写作进度时出错: {e}")

    # 检查是否有错误信息
    if "error" in feedback_data:
        st.error(f"批改过程中出现错误: {feedback_data['error']}")
        return
        
    # 检查是否是原始文本（无法解析为JSON）
    if "formatted_text" in feedback_data:
        with st.expander("原始响应（可能格式不正确）"):
            st.text(feedback_data["formatted_text"])
        st.warning("无法正常解析批改结果，请稍后再试")
        return
    
    # 总体分数
    if "overall_score" in feedback_data:
        try:
            overall_score = float(feedback_data["overall_score"])
            st.metric("总体分数", f"{overall_score:.1f}/9.0")

            # 分数评估
            if overall_score >= 7.0:
                st.success("优秀！继续保持")
            elif overall_score >= 6.0:
                st.info("良好！有提升空间")
            else:
                st.warning("需要加强练习")
        except (ValueError, TypeError):
            st.info("无法获取有效的总体分数")

    # 分数段描述
    if "band_description" in feedback_data:
        st.write("**分数段说明:**", feedback_data["band_description"])

    # 各项评分标准 - 更新为匹配新格式
    if task_type == "Task 1":
        criteria_keys = ["task_achievement", "coherence_cohesion", "lexical_resource", "grammatical_range"]
        criteria_names = ["任务完成度", "连贯与衔接", "词汇资源", "语法范围与准确性"]
    else:
        criteria_keys = ["task_response", "coherence_cohesion", "lexical_resource", "grammatical_range"]
        criteria_names = ["任务回应", "连贯与衔接", "词汇资源", "语法范围与准确性"]

    # 显示各项分数
    try:
        cols = st.columns(4)
        for i, (key, name) in enumerate(zip(criteria_keys, criteria_names)):
            if key in feedback_data and isinstance(feedback_data[key], dict) and "score" in feedback_data[key]:
                try:
                    score = float(feedback_data[key]["score"])
                    with cols[i]:
                        st.metric(name, f"{score:.1f}")
                except (ValueError, TypeError):
                    with cols[i]:
                        st.metric(name, "N/A")
    except Exception:
        st.info("无法显示详细评分")

    # 全局优缺点显示
    st.subheader("📝 总体评价")
    col1, col2 = st.columns(2)
    
    with col1:
        if "strengths" in feedback_data and feedback_data["strengths"]:
            st.write("✅ **优点:**")
            for strength in feedback_data["strengths"]:
                st.write(f"• {strength}")

    with col2:
        if "improvements" in feedback_data and feedback_data["improvements"]:
            st.write("🎯 **改进建议:**")
            for improvement in feedback_data["improvements"]:
                st.write(f"• {improvement}")

    # 语法和词汇修正
    if "suggested_corrections" in feedback_data:
        with st.expander("✏️ 语法和词汇修正建议"):
            st.write(feedback_data["suggested_corrections"])

    # 详细分析 - 各项标准
    st.subheader("🔍 各项标准详细分析")
    
    for key, name in zip(criteria_keys, criteria_names):
        if key in feedback_data and isinstance(feedback_data[key], dict):
            with st.expander(f"{name}分析"):
                criterion = feedback_data[key]

                if "comments" in criterion:
                    st.write("**评价:**", criterion["comments"])
                elif "assessment" in criterion:
                    st.write("**评价:**", criterion["assessment"])

                # 各标准的具体优点和改进点
                if "strengths" in criterion and criterion["strengths"]:
                    st.write("**优点:**")
                    for strength in criterion["strengths"]:
                        st.write(f"• {strength}")

                if "improvements" in criterion and criterion["improvements"]:
                    st.write("**改进建议:**")
                    for improvement in criterion["improvements"]:
                        st.write(f"• {improvement}")

    # 修正后的作文
    if "corrected_essay" in feedback_data:
        with st.expander("📖 修正后的作文"):
            st.write(feedback_data["corrected_essay"])

    # 范文示例
    if "model_answer" in feedback_data or "model_essay" in feedback_data:
        with st.expander("🌟 范文示例"):
            model_content = feedback_data.get("model_answer", feedback_data.get("model_essay", ""))
            st.write(model_content)

    # 重点词汇
    if "key_vocabulary" in feedback_data and feedback_data["key_vocabulary"]:
        with st.expander("📚 重点词汇"):
            vocab_cols = st.columns(3)
            vocab_list = feedback_data["key_vocabulary"]
            for i, word in enumerate(vocab_list):
                vocab_cols[i % 3].code(word)
    
    # 添加刷新按钮
    if st.button("🔄 重新加载批改结果"):
        if "current_writing_feedback" in st.session_state:
            del st.session_state["current_writing_feedback"]
        st.experimental_rerun()


def _display_record_result_data(result_data):
    """Properly render saved result_data from learning records."""
    if not isinstance(result_data, dict):
        st.text(str(result_data))
        return

    if result_data.get("cue_card"):
        with st.expander("题目卡", expanded=True):
            st.markdown(result_data["cue_card"])

    if result_data.get("question"):
        task_type = result_data.get("task_type", "")
        title = "作文题目"
        if task_type == "Task 1":
            title = "小作文题目"
        elif task_type == "Task 2":
            title = "大作文题目"
        with st.expander(title, expanded=True):
            if result_data.get("chart_type"):
                st.markdown(f"**图表类型：** {result_data['chart_type']}")
            if result_data.get("chart_image"):
                if st.button("显示/隐藏图片", key=f"chart_img_{abs(hash(result_data.get('chart_image','')))}"):
                    st.session_state[f"show_{result_data['chart_image']}"] = not st.session_state.get(f"show_{result_data['chart_image']}", False)
                if st.session_state.get(f"show_{result_data['chart_image']}", False):
                    st.image(os.path.join(os.path.dirname(__file__), result_data["chart_image"]))
            if result_data.get("topic_category"):
                st.markdown(f"**话题类别：** {result_data['topic_category']}")
            if result_data.get("essay_type"):
                st.markdown(f"**作文类型：** {result_data['essay_type']}")
            st.markdown(f"**题目：** {result_data['question']}")
            if result_data.get("key_features"):
                st.markdown("**关键特征：**")
                for item in result_data["key_features"]:
                    st.markdown(f"- {item}")
            if result_data.get("key_points"):
                st.markdown("**关键论点：**")
                for item in result_data["key_points"]:
                    st.markdown(f"- {item}")
            if result_data.get("suggested_structure"):
                st.markdown(f"**建议结构：** {result_data['suggested_structure']}")
            if result_data.get("chart_data"):
                with st.expander("表格数据（供 AI 互动使用）"):
                    st.dataframe(pd.DataFrame(result_data["chart_data"]), use_container_width=True)

    if isinstance(result_data.get("questions"), list):
        for i, item in enumerate(result_data["questions"], 1):
            if not isinstance(item, dict):
                continue
            with st.expander(f"Part 1 题目 {i}", expanded=i == 1):
                st.markdown(f"**题目：** {item.get('question', '')}")
                if item.get("keywords"):
                    st.markdown("**关键词：**")
                    for word in item["keywords"]:
                        st.markdown(f"- {word}")
                if item.get("tips"):
                    st.markdown("**回答技巧：**")
                    for tip in item["tips"]:
                        st.markdown(f"- {tip}")
                if item.get("model_answer"):
                    with st.expander("参考答案"):
                        st.write(item["model_answer"])

    if isinstance(result_data.get("discussion_questions"), list):
        for i, item in enumerate(result_data["discussion_questions"], 1):
            if not isinstance(item, dict):
                continue
            with st.expander(f"Part 3 题目 {i}", expanded=i == 1):
                st.markdown(f"**题目：** {item.get('question', '')}")
                if item.get("purpose"):
                    st.markdown(f"**考察点：** {item['purpose']}")
                if item.get("depth_required"):
                    st.markdown(f"**回答深度：** {item['depth_required']}")
                if item.get("model_response"):
                    with st.expander("参考回答"):
                        st.write(item["model_response"])

    model_answer = result_data.get("model_answer")
    if isinstance(model_answer, dict):
        with st.expander("参考答案"):
            labels = {
                "introduction": "开头",
                "main_points": "主要观点",
                "details": "细节展开",
                "conclusion": "结尾",
            }
            for key in ["introduction", "main_points", "details", "conclusion"]:
                value = model_answer.get(key)
                if not value:
                    continue
                st.markdown(f"**{labels[key]}：**")
                if isinstance(value, list):
                    for item in value:
                        st.markdown(f"- {item}")
                else:
                    st.write(value)
            answer_text = []
            for key in ["introduction", "main_points", "details", "conclusion"]:
                value = model_answer.get(key)
                if isinstance(value, list):
                    answer_text.extend(str(item) for item in value)
                elif value:
                    answer_text.append(str(value))
    elif isinstance(model_answer, str) and model_answer.strip():
        with st.expander("参考答案"):
            st.write(model_answer)

    for key, label in {
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
    }.items():
        value = result_data.get(key)
        if value:
            with st.expander(label):
                if isinstance(value, list):
                    for item in value:
                        st.markdown(f"- {item}")
                else:
                    st.write(value)

    for key, label in {
        "overall_score": "总分",
        "band_description": "分数段说明",
        "suggested_corrections": "修改建议",
        "corrected_essay": "修正后作文",
        "model_essay": "参考范文",
        "full_answer": "完整答案",
        "answer_structure": "答案结构",
        "improvement_tips": "改进建议",
        "formatted_text": "内容",
    }.items():
        value = result_data.get(key)
        if value:
            with st.expander(label):
                if key == "full_answer":
                    st.write(value)
                elif key == "formatted_text":
                    cleaned = str(value).replace("无法解析为JSON格式的响应:\n\n", "")
                    st.markdown(cleaned)
                else:
                    st.write(value)


# 显示口语反馈的函数
def _display_speaking_feedback(feedback_data):
    st.markdown("---")
    st.subheader("🎯 口语反馈")
    
    # 保存用户进度记录
    try:
        if "overall_score" in feedback_data:
            user_id = st.session_state.user_profile.get("user_id", "default_user")
            # 确保分数符合雅思格式
            score = float(feedback_data["overall_score"])
            # 将分数舍入为符合雅思标准的0.5分间隔格式
            formatted_score = round(score * 2) / 2
            save_user_progress(
                user_id=user_id,
                activity="口语练习",
                data={
                    "score": formatted_score,
                    "timestamp": datetime.now().isoformat()
                }
            )
    except Exception as e:
        print(f"保存口语进度时出错: {e}")

    # 总体分数
    if "overall_score" in feedback_data:
        overall_score = feedback_data["overall_score"]
        st.metric("总体分数", f"{overall_score:.1f}/9.0")

        # 分数评估
        if overall_score >= 7.0:
            st.success("流利自然，表达准确")
        elif overall_score >= 6.0:
            st.info("基本流利，有提升空间")
        else:
            st.warning("需要加强练习")

    # 各项评分
    if "breakdown" in feedback_data:
        breakdown = feedback_data["breakdown"]
        criteria = [
            ("fluency_coherence", "流利度与连贯性"),
            ("lexical_resource", "词汇资源"),
            ("grammatical_range_accuracy", "语法范围与准确性"),
            ("pronunciation", "发音")
        ]

        cols = st.columns(4)
        for i, (key, name) in enumerate(criteria):
            if key in breakdown and "score" in breakdown[key]:
                score = breakdown[key]["score"]
                with cols[i]:
                    st.metric(name, f"{score:.1f}")

        # 详细分析
        for key, name in criteria:
            if key in breakdown:
                with st.expander(f"{name}分析"):
                    criterion = breakdown[key]

                    if "strengths" in criterion and criterion["strengths"]:
                        st.write("✅ **优点:**")
                        for strength in criterion["strengths"]:
                            st.write(f"• {strength}")

                    if "weaknesses" in criterion and criterion["weaknesses"]:
                        st.write("🎯 **待改进:**")
                        for weakness in criterion["weaknesses"]:
                            st.write(f"• {weakness}")

                    if "suggestions" in criterion and criterion["suggestions"]:
                        st.write("💡 **建议:**")
                        for suggestion in criterion["suggestions"]:
                            st.write(f"• {suggestion}")

                    # 特定功能的显示
                    if key == "lexical_resource" and "suggested_words" in criterion:
                        st.write("📚 **推荐词汇:**")
                        word_cols = st.columns(3)
                        words = criterion["suggested_words"]
                        for i, word in enumerate(words):
                            word_cols[i % 3].code(word)

    # 优化后的回答
    if "improved_response" in feedback_data:
        with st.expander("✨ 优化后的回答示例"):
            st.write(feedback_data["improved_response"])

    # 练习建议
    if "practice_recommendations" in feedback_data and feedback_data["practice_recommendations"]:
        with st.expander("📋 练习建议"):
            for recommendation in feedback_data["practice_recommendations"]:
                st.write(f"• {recommendation}")


# 工具函数 (utils.py) - 补充完整
def validate_essay_length(essay_content: str, min_words: int = 150, max_words: int = 300) -> tuple:
    """验证作文字数"""
    # 简单的字数统计（实际应用中可以使用更准确的方法）
    words = re.findall(r'\b\w+\b', essay_content)
    word_count = len(words)

    if word_count < min_words:
        return False, f"作文字数不足（{word_count}字），建议至少{min_words}字"
    elif word_count > max_words:
        return False, f"作文字数超过限制（{word_count}字），建议控制在{max_words}字以内"
    else:
        return True, f"字数合适（{word_count}字）"


def create_score_gauge(score: float, max_score: float = 9.0) -> str:
    """创建分数仪表盘显示"""
    percentage = (score / max_score) * 100
    if score >= 7.0:
        color = "🟢"  # 绿色
        level = "优秀"
    elif score >= 6.0:
        color = "🟡"  # 黄色
        level = "良好"
    elif score >= 5.0:
        color = "🟠"  # 橙色
        level = "及格"
    else:
        color = "🔴"  # 红色
        level = "需提高"

    return f"{color} {score:.1f}/9.0 ({level})"




def parse_json_response(response_text: str):
    """解析JSON格式的响应"""
    try:
        # 尝试直接解析JSON
        return json.loads(response_text)
    except json.JSONDecodeError:
        # 如果失败，尝试提取JSON部分
        try:
            # 清理可能的代码标记
            cleaned_text = response_text.replace('```json', '').replace('```', '').strip()
            # 尝试找到第一个{和最后一个}
            start = cleaned_text.find('{')
            end = cleaned_text.rfind('}') + 1
            if start != -1 and end != 0:
                json_str = cleaned_text[start:end]
                return json.loads(json_str)
        except:
            pass

    # 如果无法解析为JSON，返回原始文本
    return {"answer": response_text}

# 初始化session state
def initialize_session_state():
    if "tongyi_agent" not in st.session_state:
        st.session_state.tongyi_agent = None
    if "dashscope_api_key" not in st.session_state:
        st.session_state.dashscope_api_key = os.getenv("DASHSCOPE_API_KEY", "")
    if "ai_provider" not in st.session_state:
        st.session_state.ai_provider = "tongyi"
    if "ai_model" not in st.session_state:
        st.session_state.ai_model = AI_PROVIDERS["tongyi"]["default_model"]
    if "ai_base_url" not in st.session_state:
        st.session_state.ai_base_url = ""
    if "ai_api_keys" not in st.session_state:
        st.session_state.ai_api_keys = {}
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "login_user_id" not in st.session_state:
        st.session_state.login_user_id = ""
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "user_progress" not in st.session_state:
        st.session_state.user_progress = []
    if "user_profile" not in st.session_state:
        st.session_state.user_profile = {
            "user_id": os.getenv("IELTS_DEFAULT_USER_ID", "default_user"),
            "current_level": 5.0,
            "listening_level": 5.0,
            "speaking_level": 5.0,
            "reading_level": 5.0,
            "writing_level": 5.0,
            "target_score": 6.5,
            "weak_areas": ["口语", "写作"],
            "study_time": 10,
            "exam_date": ""
        }
    if "current_user_id" not in st.session_state:
        st.session_state.current_user_id = st.session_state.user_profile.get("user_id", "default_user")
    if "database_initialized" not in st.session_state:
        st.session_state.database_initialized = initialize_database()
    if "current_speaking_part" not in st.session_state:
        st.session_state.current_speaking_part = "Part 1"
    if "theme_linking_topics" not in st.session_state:
        st.session_state.theme_linking_topics = []
    if "latest_part2_topic" not in st.session_state:
        st.session_state.latest_part2_topic = ""
    if "latest_part2_question" not in st.session_state:
        st.session_state.latest_part2_question = None
    if "part3_question_generated" not in st.session_state:
        st.session_state.part3_question_generated = False
    # 计时器状态初始化
    if "timer_active" not in st.session_state:
        st.session_state.timer_active = False
    if "timer_type" not in st.session_state:
        st.session_state.timer_type = None
    if "remaining_time" not in st.session_state:
        st.session_state.remaining_time = 0
    if "improvement_suggestions" not in st.session_state:
        st.session_state.improvement_suggestions = None


def _default_user_profile(user_id: str) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "current_level": 5.0,
        "listening_level": 5.0,
        "speaking_level": 5.0,
        "reading_level": 5.0,
        "writing_level": 5.0,
        "target_score": 6.5,
        "weak_areas": ["口语", "写作"],
        "study_time": 10,
        "exam_date": ""
    }


def _initialize_agent_from_api_key(api_key: str, provider: str = "tongyi", model: str = "", base_url: str = "") -> bool:
    if not api_key:
        st.session_state.tongyi_agent = None
        return False

    try:
        st.session_state.tongyi_agent = TongyiIELTSAssistant(
            api_key,
            provider=provider,
            model=model or AI_PROVIDERS.get(provider, AI_PROVIDERS["tongyi"])["default_model"],
            base_url=base_url or AI_PROVIDERS.get(provider, {}).get("base_url", "")
        )
        return True
    except Exception as e:
        st.session_state.tongyi_agent = None
        st.error(f"Agent初始化失败: {str(e)}")
        return False


def _render_login_page():
    st.title("🎓 信达雅")

    db_status = get_database_status()
    if not db_status["connected"]:
        if db_status["enabled"]:
            st.warning(db_status["message"])
        else:
            st.info("当前未启用 MySQL。可以临时登录体验，但 API Key 无法跨重启持久保存。")

    flask_cross_url = f"{_flask_base_url()}?user_id={st.session_state.get('login_user_id', '')}&x_token={_cross_login_token(st.session_state.get('login_user_id', ''))}"
    st.link_button("进入 Beta 版", flask_cross_url, use_container_width=True)

    login_tab, register_tab = st.tabs(["登录", "注册"])

    with login_tab:
        with st.form("login_form"):
            default_id = st.session_state.get("login_user_id", "") or _load_last_user() or os.getenv("IELTS_DEFAULT_USER_ID", "")
            user_id = st.text_input(
                "用户ID",
                value=default_id,
                key="login_form_user_id"
            ).strip()
            password = st.text_input("登录密码", type="password", key="login_form_password")
            submitted = st.form_submit_button("登录", type="primary")

        if submitted:
            if not user_id or not password:
                st.error("请输入用户ID和登录密码")
                return

            if not authenticate_user(user_id, password):
                st.error("用户不存在或密码不正确，请先注册")
                return

            _save_last_user(user_id)
            st.session_state.authenticated = True
            st.session_state.login_user_id = user_id
            st.session_state.current_user_id = user_id
            st.session_state.user_profile = load_user_profile(user_id) or _default_user_profile(user_id)
            ai_config = load_user_ai_config(user_id)
            st.session_state.ai_provider = ai_config.get("provider", "tongyi")
            st.session_state.ai_model = ai_config.get("model", AI_PROVIDERS["tongyi"]["default_model"])
            st.session_state.ai_base_url = ai_config.get("base_url", "")
            st.session_state.ai_api_keys = ai_config.get("api_keys", {})
            env_key = AI_PROVIDERS.get(st.session_state.ai_provider, {}).get("env_key", "")
            st.session_state.dashscope_api_key = ai_config.get("api_key", "") or (os.getenv(env_key, "") if env_key else "")
            if st.session_state.dashscope_api_key:
                _initialize_agent_from_api_key(
                    st.session_state.dashscope_api_key,
                    st.session_state.ai_provider,
                    st.session_state.ai_model,
                    st.session_state.ai_base_url
                )
            st.query_params["user_id"] = user_id
            st.query_params["x_token"] = _cross_login_token(user_id)
            st.rerun()

    with register_tab:
        with st.form("register_form"):
            new_user_id = st.text_input(
                "新用户ID",
                placeholder="例如：ielts",
                key="register_form_user_id"
            ).strip()
            new_password = st.text_input("设置密码", type="password", key="register_form_password")
            confirm_password = st.text_input("确认密码", type="password", key="register_form_confirm_password")
            register_submitted = st.form_submit_button("注册", type="primary")

        if register_submitted:
            if not new_user_id or not new_password:
                st.error("请输入新用户ID和密码")
                return
            if len(new_user_id) > 64:
                st.error("用户ID不能超过64个字符")
                return
            if len(new_password) < 4:
                st.error("密码至少需要4位")
                return
            if new_password != confirm_password:
                st.error("两次输入的密码不一致")
                return

            if not register_user(new_user_id, new_password):
                st.error("该用户ID已存在，请换一个用户ID或直接登录")
                return

            _save_last_user(new_user_id)
            st.session_state.login_user_id = new_user_id
            st.session_state.current_user_id = new_user_id
            st.session_state.authenticated = True
            st.session_state.user_profile = load_user_profile(new_user_id) or _default_user_profile(new_user_id)
            st.session_state.ai_provider = "tongyi"
            st.session_state.ai_model = AI_PROVIDERS["tongyi"]["default_model"]
            st.session_state.ai_base_url = ""
            st.session_state.dashscope_api_key = os.getenv("DASHSCOPE_API_KEY", "")
            if st.session_state.dashscope_api_key:
                _initialize_agent_from_api_key(
                    st.session_state.dashscope_api_key,
                    st.session_state.ai_provider,
                    st.session_state.ai_model,
                    st.session_state.ai_base_url
                )
            st.success("注册成功，已自动登录")
            st.query_params["user_id"] = new_user_id
            st.query_params["x_token"] = _cross_login_token(new_user_id)
            st.rerun()


initialize_session_state()

# 跨版本自动登录：来自 Flask 的 x_token 校验
if not st.session_state.authenticated:
    params = st.query_params
    x_user = params.get("user_id", "").strip()
    x_token = params.get("x_token", "")
    if x_user and x_token and _verify_cross_token(x_user, x_token):
        profile = load_user_profile(x_user)
        if profile:
            _save_last_user(x_user)
            st.session_state.authenticated = True
            st.session_state.login_user_id = x_user
            st.session_state.current_user_id = x_user
            st.session_state.user_profile = profile
            ai_config = load_user_ai_config(x_user)
            st.session_state.ai_provider = ai_config.get("provider", "tongyi")
            st.session_state.ai_model = ai_config.get("model", AI_PROVIDERS["tongyi"]["default_model"])
            st.session_state.ai_base_url = ai_config.get("base_url", "")
            st.session_state.ai_api_keys = ai_config.get("api_keys", {})
            env_key = AI_PROVIDERS.get(st.session_state.ai_provider, {}).get("env_key", "")
            st.session_state.dashscope_api_key = ai_config.get("api_key", "") or (os.getenv(env_key, "") if env_key else "")
            if st.session_state.dashscope_api_key:
                _initialize_agent_from_api_key(
                    st.session_state.dashscope_api_key,
                    st.session_state.ai_provider,
                    st.session_state.ai_model,
                    st.session_state.ai_base_url
                )
            st.query_params["user_id"] = x_user
            st.query_params["x_token"] = x_token
            st.rerun()
    else:
        _render_login_page()
        st.stop()

# 侧边栏设置
with st.sidebar:
    st.title("🔧 设置")

    db_status = get_database_status()
    if not db_status["connected"]:
        if db_status["enabled"]:
            st.warning(f"⚠️ {db_status['message']}")
        else:
            st.info(db_status["message"])

    st.markdown("---")

    st.title("🔐 当前用户")
    st.write(f"用户ID：`{st.session_state.current_user_id}`")
    flask_cross_url = f"{_flask_base_url()}?user_id={st.session_state.current_user_id}&x_token={_cross_login_token(st.session_state.current_user_id)}"
    st.link_button("进入 Beta 版", flask_cross_url, use_container_width=True)
    if st.button("退出登录", use_container_width=True):
        st.query_params.clear()
        st.session_state.authenticated = False
        st.session_state.login_user_id = ""
        st.session_state.tongyi_agent = None
        st.session_state.dashscope_api_key = ""
        st.rerun()

    st.markdown("---")

    # AI API密钥设置
    st.title("🔑 API配置")
    provider_options = [config["label"] for config in AI_PROVIDERS.values()]
    current_provider = st.session_state.get("ai_provider", "tongyi")
    provider_label = st.selectbox(
        "AI供应商",
        provider_options,
        index=provider_options.index(_provider_label(current_provider)),
        help="DeepSeek和自定义接口使用OpenAI兼容格式"
    )
    selected_provider = _provider_from_label(provider_label)
    selected_defaults = AI_PROVIDERS[selected_provider]

    stored_keys = st.session_state.get("ai_api_keys", {})
    current_provider_key = stored_keys.get(selected_provider, "")
    env_key_name = selected_defaults.get("env_key", "")
    env_api_key = os.getenv(env_key_name, "") if env_key_name else ""

    model_value = st.text_input(
        "模型名称",
        value=st.session_state.get("ai_model", selected_defaults["default_model"])
        if selected_provider == st.session_state.get("ai_provider", "tongyi")
        else selected_defaults["default_model"],
        help="例如：qwen-turbo、deepseek-chat、gpt-4o-mini"
    )

    base_url_value = ""
    if selected_provider in {"deepseek", "custom"}:
        base_url_value = st.text_input(
            "Base URL",
            value=st.session_state.get("ai_base_url", selected_defaults["base_url"])
            if selected_provider == st.session_state.get("ai_provider", "tongyi")
            else selected_defaults["base_url"],
            help="OpenAI兼容接口地址，例如 https://api.deepseek.com"
        )

    api_key = st.text_input(
        f"{provider_label} API Key",
        type="password",
        value=current_provider_key or (
            st.session_state.dashscope_api_key if selected_provider == st.session_state.get("ai_provider", "tongyi") else env_api_key
        ),
        help="登录后保存到当前用户，下次登录自动加载该供应商配置",
        placeholder="sk-..."
    )

    if st.button("保存当前用户AI配置", type="primary", use_container_width=True):
        if not api_key:
            st.warning("请输入API Key后再保存")
        else:
            st.session_state.dashscope_api_key = api_key
            saved_to_mysql = save_user_ai_config(
                st.session_state.current_user_id,
                selected_provider,
                api_key,
                model_value,
                base_url_value
            )
            if _initialize_agent_from_api_key(api_key, selected_provider, model_value, base_url_value):
                if saved_to_mysql:
                    st.success("AI配置已保存到当前用户，并完成 Agent 初始化")
                else:
                    st.success("AI配置已在当前会话中生效")

    if st.session_state.tongyi_agent:
        st.success(f"✅ Agent 已就绪：{_provider_label(st.session_state.get('ai_provider', 'tongyi'))}")
    else:
        st.warning("请先保存当前用户的 AI API Key")

    st.markdown("---")

    # 用户档案
    st.title("👤 用户档案")
    selected_user_id = st.session_state.current_user_id

    with st.form("user_profile_form"):
        user_id = selected_user_id
        fallback_level = float(st.session_state.user_profile.get("current_level", 5.0))
        st.write("**当前雅思水平**")
        level_col1, level_col2 = st.columns(2)
        with level_col1:
            listening_level = st.slider(
                "听力",
                1.0,
                9.0,
                float(st.session_state.user_profile.get("listening_level", fallback_level)),
                0.5,
                key="profile_listening_level"
            )
            speaking_level = st.slider(
                "口语",
                1.0,
                9.0,
                float(st.session_state.user_profile.get("speaking_level", fallback_level)),
                0.5,
                key="profile_speaking_level"
            )
        with level_col2:
            reading_level = st.slider(
                "阅读",
                1.0,
                9.0,
                float(st.session_state.user_profile.get("reading_level", fallback_level)),
                0.5,
                key="profile_reading_level"
            )
            writing_level = st.slider(
                "写作",
                1.0,
                9.0,
                float(st.session_state.user_profile.get("writing_level", fallback_level)),
                0.5,
                key="profile_writing_level"
            )

        current_level = _round_to_ielts_band((listening_level + speaking_level + reading_level + writing_level) / 4)
        st.caption(f"综合当前水平：{current_level:.1f}分")

        target_score = st.slider("目标总分", 1.0, 9.0,
                                 float(st.session_state.user_profile["target_score"]), 0.5, key="profile_target_score")

        study_time = st.slider("每周学习时间(小时)", 1, 40,
                               st.session_state.user_profile["study_time"], key="profile_study_time")

        weak_areas = st.multiselect(
            "弱项领域",
            ["听力", "阅读", "写作", "口语"],
            default=st.session_state.user_profile["weak_areas"]
        )

        try:
            saved_exam_date = st.session_state.user_profile.get("exam_date", "")
            exam_date_value = datetime.strptime(saved_exam_date, "%Y-%m-%d").date() if saved_exam_date else datetime.now().date() + pd.Timedelta(days=30)
        except (ValueError, TypeError):
            exam_date_value = datetime.now().date() + pd.Timedelta(days=30)

        exam_date = st.date_input("考试日期", value=exam_date_value)

        if st.form_submit_button("更新档案"):
            updated_profile = {
                "user_id": user_id,
                "current_level": current_level,
                "listening_level": listening_level,
                "speaking_level": speaking_level,
                "reading_level": reading_level,
                "writing_level": writing_level,
                "target_score": target_score,
                "weak_areas": weak_areas,
                "study_time": study_time,
                "exam_date": exam_date.strftime("%Y-%m-%d")
            }
            saved_to_mysql = save_user_profile(user_id, updated_profile)
            st.session_state.current_user_id = user_id
            if saved_to_mysql:
                st.success("用户档案已更新并保存到 MySQL！")
            else:
                st.success("用户档案已更新！")

    st.markdown("---")
    st.title("💡 快速导航")

    # 快速导航按钮
    if st.button("🎯 口语串题", use_container_width=True):
        st.session_state.active_tab = "🔗 口语串题"
        st.rerun()

    if st.button("📝 作文批改", use_container_width=True):
        st.session_state.active_tab = "📝 作文批改"
        st.rerun()

    if st.button("💬 口语练习", use_container_width=True):
        st.session_state.active_tab = "💬 口语练习"
        st.rerun()

    st.markdown("---")
    with st.expander("ℹ️ 稳定版功能", expanded=False):
        st.markdown("""
**稳定版（当前）**
- 🏠 学习进度概览与弱项分析
- 💬 口语三部分练习（Part 1/2/3）
- 🔗 口语串题训练
- 📝 作文批改（Task 1 + Task 2）
- 📊 学习分析与练习历史
- 📅 学习记录日历筛选与回练
- 🔑 多 AI 供应商支持（通义/DeepSeek/自定义）
- 🔐 跨版本免登录
        """.strip())

    st.markdown("---")
    st.caption("👆 Beta 版额外支持：语音朗读、语音输入/录音评分、写作题目图表、学习建议 AI 生成")
    st.caption("版本: 2.0 · Beta: 2.0")

# 主界面
st.title("🎓 信达雅 ")

# 功能选项卡 — 用按钮模拟 tabs，支持快速开始跳转
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "🏠 首页"

TABS = ["🏠 首页", "💬 口语练习", "🔗 口语串题", "📝 作文批改", "📊 学习分析"]
tab_cols = st.columns(len(TABS))
for idx, (col, label) in enumerate(zip(tab_cols, TABS)):
    with col:
        is_active = st.session_state.active_tab == label
        if st.button(
            label,
            use_container_width=True,
            type="primary" if is_active else "secondary",
            key=f"tabbtn_{idx}"
        ):
            st.session_state.active_tab = label
            st.rerun()

# 首页
if st.session_state.active_tab.startswith("🏠"):
    st.header("欢迎使用信达雅！")

    if not st.session_state.tongyi_agent:
        st.warning("⚠️ 请先在侧边栏配置并保存AI API Key以使用全部功能")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📈 学习进度概览")
        current_level = _profile_overall_level(st.session_state.user_profile)
        target_score = st.session_state.user_profile["target_score"]

        st.metric("当前综合水平", f"{current_level:.1f}分")
        st.metric("目标分数", f"{target_score:.1f}分")
        st.metric("需要提升", f"{(target_score - current_level):.1f}分")

        # 进度可视化
        progress = min((current_level - 1) / 8 * 100, 100)
        st.progress(int(progress))
        st.caption(f"进度: {progress:.1f}%")

        # 弱项分析
        if st.session_state.user_profile["weak_areas"]:
            st.subheader("🎯 重点提升领域")
            for area in st.session_state.user_profile["weak_areas"]:
                st.info(f"• {area}")

    with col2:
        st.subheader("🚀 快速开始练习")

        # 口语练习快速入口
        st.write("**口语练习**")
        col2a, col2b, col2c = st.columns(3)
        with col2a:
            if st.button("Part 1", use_container_width=True):
                st.session_state.active_tab = "💬 口语练习"
                st.session_state.current_speaking_part = "Part 1"
                st.rerun()
        with col2b:
            if st.button("Part 2", use_container_width=True):
                st.session_state.active_tab = "💬 口语练习"
                st.session_state.current_speaking_part = "Part 2"
                st.rerun()
        with col2c:
            if st.button("Part 3", use_container_width=True):
                st.session_state.active_tab = "💬 口语练习"
                st.session_state.current_speaking_part = "Part 3"
                st.rerun()

        st.markdown("---")

        # 作文批改进口
        st.write("**作文批改**")
        col2d, col2e = st.columns(2)
        with col2d:
            if st.button("小作文", use_container_width=True):
                st.session_state.active_tab = "📝 作文批改"
                st.session_state.writing_task_type = "Task 1"
                st.rerun()
        with col2e:
            if st.button("大作文", use_container_width=True):
                st.session_state.active_tab = "📝 作文批改"
                st.session_state.writing_task_type = "Task 2"
                st.rerun()

        st.markdown("---")

        # 口语串题入口
        if st.button("🔗 开始口语串题", use_container_width=True):
            st.session_state.active_tab = "🔗 口语串题"
            st.rerun()

# 口语练习标签页
if st.session_state.active_tab.startswith("💬"):
    st.header("💬 雅思口语练习")

    if not st.session_state.tongyi_agent:
        st.warning("请先在侧边栏配置并保存AI API Key")
    else:
        # 口语部分选择
        st.subheader("选择口语部分")
        part_col1, part_col2, part_col3 = st.columns(3)

        with part_col1:
            if st.button("Part 1: 自我介绍", use_container_width=True):
                st.session_state.current_speaking_part = "Part 1"
        with part_col2:
            if st.button("Part 2: 个人陈述", use_container_width=True):
                st.session_state.current_speaking_part = "Part 2"
        with part_col3:
            if st.button("Part 3: 深入讨论", use_container_width=True):
                st.session_state.current_speaking_part = "Part 3"

        st.markdown(f"### 🎯 当前练习: {st.session_state.current_speaking_part}")

        # 根据选择的部分显示不同的界面
        if st.session_state.current_speaking_part == "Part 1":
            _render_speaking_part1()
        elif st.session_state.current_speaking_part == "Part 2":
            _render_speaking_part2()
        else:
            _render_speaking_part3()

# 口语串题标签页
if st.session_state.active_tab.startswith("🔗"):
    st.header("🔗 雅思口语串题训练")

    if not st.session_state.tongyi_agent:
        st.warning("请先在侧边栏配置并保存AI API Key")
    else:
        st.info("💡 口语串题技巧：将多个话题用一个核心故事串联，减少记忆负担，提高回答一致性")

        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("串题配置")

            # 选择要串联的话题
            available_topics = [
                "描述一个重要的决定", "谈论一次旅行经历", "描述一个敬佩的人",
                "讨论一个环境问题", "讲述一个学习经历", "描述一个传统节日",
                "谈论科技的影响", "讨论健康生活方式", "描述一个历史事件"
            ]

            selected_topics = st.multiselect(
                "选择要串联的话题（至少选择2个）",
                available_topics,
                default=st.session_state.theme_linking_topics,
                max_selections=5
            )

            main_theme = st.text_input(
                "核心主题（用于串联所有话题）",
                placeholder="例如：个人成长、环境保护、文化交流等",
                help="用一个统一的主题将所有话题有机联系起来"
            )

            target_score = st.slider("目标分数", 5.0, 8.0, 6.5, 0.5, key="speaking_theme_target_score")

            if st.button("🔗 生成串题方案", type="primary") and len(selected_topics) >= 2 and main_theme:
                with st.spinner("正在生成口语串题方案..."):
                    try:
                        result = st.session_state.tongyi_agent.link_speaking_themes(
                            topics=selected_topics,
                            main_theme=main_theme,
                            target_score=target_score
                        )

                        st.session_state.theme_linking_result = parse_json_response(result)
                        st.session_state.theme_linking_topics = selected_topics

                    except Exception as e:
                        st.error(f"生成串题方案时出错: {str(e)}")

        with col2:
            st.subheader("串题技巧")
            st.write("""
            **优势：**
            - ✅ 减少记忆负担
            - ✅ 提高回答一致性
            - ✅ 展现语言灵活性
            - ✅ 增强故事连贯性

            **注意事项：**
            - ⚠️ 确保自然过渡
            - ⚠️ 避免生硬连接
            - ⚠️ 保持话题相关性
            """)

        # 显示串题结果
        if "theme_linking_result" in st.session_state:
            st.markdown("---")
            st.subheader("🎯 串题方案")

            result = st.session_state.theme_linking_result

            # 显示核心主题（中英文）
            col1, col2 = st.columns(2)
            with col1:
                if "unifying_theme" in result:
                    st.success(f"**核心主题:** {result['unifying_theme']}")
            with col2:
                if "unifying_theme_en" in result:
                    st.success(f"**Core Theme:** {result['unifying_theme_en']}")

            # 显示各个话题的回答（中英文）
            if "linked_responses" in result:
                for i, response in enumerate(result['linked_responses']):
                    # 创建带有中英文标题的expander
                    topic_title = response.get('topic', '未知话题')
                    topic_title_en = response.get('topic_en', 'Unknown Topic')
                    with st.expander(f"话题 {i + 1}: {topic_title} / {topic_title_en}"):
                        # 中文回答
                        if "adapted_response" in response:
                            st.write("**适应后的回答（中文）:**")
                            st.write(response['adapted_response'])
                            st.write("")
                        
                        # 英文回答
                        if "adapted_response_en" in response:
                            st.write("**Adapted Response (English):**")
                            st.write(response['adapted_response_en'])
                            st.write("")

                        # 关键元素（中英文）
                        key_col1, key_col2 = st.columns(2)
                        with key_col1:
                            if "key_elements" in response:
                                st.write("**关键元素:**")
                                for element in response['key_elements']:
                                    st.write(f"• {element}")
                        with key_col2:
                            if "key_elements_en" in response:
                                st.write("**Key Elements:**")
                                for element in response['key_elements_en']:
                                    st.write(f"• {element}")

                        # 过渡短语（中英文）
                        if "transition_phrases" in response or "transition_phrases_en" in response:
                            trans_col1, trans_col2 = st.columns(2)
                            with trans_col1:
                                if "transition_phrases" in response:
                                    st.write("**过渡短语:**")
                                    for phrase in response['transition_phrases']:
                                        st.markdown(f"- {phrase}")
                            with trans_col2:
                                if "transition_phrases_en" in response:
                                    st.write("**Transition Phrases:**")
                                    for phrase in response['transition_phrases_en']:
                                        st.markdown(f"- {phrase}")

            # 显示通用词汇库（中英文）
            if "versatile_vocabulary" in result or "versatile_vocabulary_en" in result:
                st.subheader("💎 通用词汇库")
                vocab_col1, vocab_col2 = st.columns(2)
                
                with vocab_col1:
                    st.write("**中文词汇:**")
                    cols = st.columns(3)
                    if "versatile_vocabulary" in result:
                        vocab_list = result['versatile_vocabulary']
                        for i, word in enumerate(vocab_list):
                            cols[i % 3].markdown(f"- {word}")
                
                with vocab_col2:
                    st.write("**English Vocabulary:**")
                    cols = st.columns(3)
                    if "versatile_vocabulary_en" in result:
                        vocab_list = result['versatile_vocabulary_en']
                        for i, word in enumerate(vocab_list):
                            cols[i % 3].markdown(f"- {word}")
            
            # 显示其他补充信息（中英文）
            if "flexible_structures" in result or "flexible_structures_en" in result:
                st.subheader("📋 灵活句式")
                struct_col1, struct_col2 = st.columns(2)
                
                with struct_col1:
                    if "flexible_structures" in result:
                        st.write("**中文句式:**")
                        for struct in result['flexible_structures']:
                            st.markdown(f"- {struct}")
                
                with struct_col2:
                    if "flexible_structures_en" in result:
                        st.write("**English Structures:**")
                        for struct in result['flexible_structures_en']:
                            st.markdown(f"- {struct}")
            
            # 记忆技巧和练习策略（中英文）
            if "memory_aids" in result or "memory_aids_en" in result or "practice_strategy" in result or "practice_strategy_en" in result:
                st.subheader("💡 学习建议")
                advice_col1, advice_col2 = st.columns(2)
                
                with advice_col1:
                    if "memory_aids" in result:
                        st.write("**记忆技巧:**")
                        for aid in result['memory_aids']:
                            st.write(f"• {aid}")
                    if "practice_strategy" in result:
                        st.write("\n**练习策略:**")
                        st.write(result['practice_strategy'])
                
                with advice_col2:
                    if "memory_aids_en" in result:
                        st.write("**Memory Aids:**")
                        for aid in result['memory_aids_en']:
                            st.write(f"• {aid}")
                    if "practice_strategy_en" in result:
                        st.write("\n**Practice Strategy:**")
                        st.write(result['practice_strategy_en'])

# 作文批改标签页
if st.session_state.active_tab.startswith("📝"):
    st.header("📝 雅思作文批改")

    if not st.session_state.tongyi_agent:
        st.warning("请先在侧边栏配置并保存AI API Key")
    else:
        st.subheader("选择作文类型")
        task_col1, task_col2 = st.columns(2)
        with task_col1:
            if st.button("📊 Task 1: 小作文", use_container_width=True):
                st.session_state.writing_task_type = "Task 1"
                st.session_state.generated_writing_topic = None
                st.rerun()
        with task_col2:
            if st.button("📝 Task 2: 大作文", use_container_width=True):
                st.session_state.writing_task_type = "Task 2"
                st.session_state.generated_writing_topic = None
                st.rerun()

        current_task = st.session_state.get("writing_task_type", "Task 2")
        st.markdown(f"### 📝 当前批改: {current_task}")

        # 根据作文类型显示不同的界面
        if current_task == "Task 1":
            _render_writing_task1()
        else:
            _render_writing_task2()

# 学习分析标签页
if st.session_state.active_tab.startswith("📊"):
    st.header("📊 学习分析报告")

    if not st.session_state.tongyi_agent:
        st.warning("请先在侧边栏配置并保存AI API Key")
    else:
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("学习时长", f"{st.session_state.user_profile['study_time']}小时/周")
        with col2:
            try:
                exam_date_str = st.session_state.user_profile.get('exam_date', '')
                if exam_date_str and exam_date_str != '':
                    days_until_exam = (datetime.strptime(exam_date_str, '%Y-%m-%d') - datetime.now()).days
                    st.metric("距离考试", f"{days_until_exam}天")
                else:
                    st.metric("距离考试", "未设置")
            except (ValueError, TypeError):
                st.metric("距离考试", "日期格式错误")
        with col3:
            improvement_needed = st.session_state.user_profile['target_score'] - _profile_overall_level(st.session_state.user_profile)
            st.metric("需要提升", f"{improvement_needed:.1f}分")

        user_id = st.session_state.user_profile.get("user_id", "default_user")
        user_progress = get_user_progress(user_id)

        st.subheader("📚 练习历史")

        # Date filter
        filter_date = st.date_input("📅 按日期筛选（清空日期显示全部）", value=None, key="history_date_filter")
        filtered_progress = user_progress
        if filter_date:
            date_str = filter_date.strftime("%Y-%m-%d")
            filtered_progress = [r for r in user_progress if (r.get("timestamp", "") or "").startswith(date_str)]

        # Replay handling from query params — removed (doesn't work with Streamlit auth)
        # Records with mode info can be replayed in Beta version (Flask) via /replay?ts=xxx

        if filtered_progress:
            recent_records = list(reversed(filtered_progress[-15:]))
            for record in recent_records:
                data = record.get("data", {}) or {}
                score = record.get("score") or data.get("score", "")
                timestamp = record.get("timestamp", "")
                activity = record.get("activity", "学习记录")
                with st.expander(f"{activity} — {timestamp}" + (f" | 得分：{score}" if score else "")):
                    flask_url = _flask_base_url()
                    user_id = st.session_state.get("login_user_id") or st.session_state.get("current_user_id", "")
                    x_token = _cross_login_token(user_id) if user_id else ""
                    record_id = record.get("id", "")
                    flask_replay = f"{flask_url}/replay?id={record_id}&user_id={user_id}&x_token={x_token}" if record_id else f"{flask_url}/replay?ts={timestamp}&user_id={user_id}&x_token={x_token}"
                    st.markdown(f"[🔄 重新练习此题]({flask_replay})")
                    if data.get("mode"):
                        st.caption(f"模式：{data['mode']}")
                    if data.get("task_type"):
                        st.caption(f"任务类型：{data['task_type']}")
                    if data.get("topics"):
                        st.caption("话题列表：")
                        st.write(", ".join(data["topics"]))
                    if data.get("topic"):
                        st.caption(f"题目/话题：{data['topic']}")
                    if data.get("question"):
                        st.caption(f"练习题：{data['question']}")
                    if data.get("feedback"):
                        st.caption(f"反馈：{data['feedback']}")
                    if data.get("user_response"):
                        st.caption("你的回答：")
                        st.text(data["user_response"][:500])
                    if data.get("essay_content"):
                        st.caption("作文内容：")
                        st.text(data["essay_content"][:500])
                    if data.get("chinese_answer"):
                        st.caption(f"中文思路：{data['chinese_answer']}")
                    if data.get("keywords"):
                        st.caption(f"关键词：{data['keywords']}")
                    if data.get("word_count"):
                        st.caption(f"字数：{data['word_count']}")
                    if data.get("score"):
                        st.caption(f"得分：{data['score']}")
                    result_data = data.get("result_data")
                    if result_data and isinstance(result_data, dict):
                        record_title = learning_record_title(activity)
                        st.markdown(f"**{record_title}：**")
                        _display_record_result_data(result_data)
                    elif data.get("result"):
                        record_title = learning_record_title(activity)
                        st.markdown(f"**{record_title}：**")
                        st.markdown(str(data["result"])[:2000])
        else:
            st.info("暂无练习记录。完成口语反馈或作文批改后，这里会自动显示历史数据。")

        # 弱项分析 - AI 生成
        st.subheader("🎯 重点提升建议")
        if st.button("🤖 生成提升建议", type="primary"):
            if not st.session_state.tongyi_agent:
                st.warning("请先在侧边栏配置并保存AI API Key")
            else:
                with st.spinner("正在根据你的训练记录生成个性化建议..."):
                    try:
                        weak_areas = st.session_state.user_profile.get("weak_areas", [])
                        if isinstance(weak_areas, str):
                            try:
                                weak_areas = json.loads(weak_areas)
                            except (TypeError, ValueError):
                                weak_areas = [weak_areas] if weak_areas else []
                        target_score = st.session_state.user_profile.get("target_score", 6.5)
                        current_level = _profile_overall_level(st.session_state.user_profile)
                        suggestions = st.session_state.tongyi_agent.generate_improvement_suggestions(
                            user_progress, weak_areas, float(target_score), float(current_level)
                        )
                        st.session_state.improvement_suggestions = suggestions
                    except Exception as e:
                        st.error(f"生成建议失败: {e}")

        if st.session_state.get("improvement_suggestions"):
            s = st.session_state.improvement_suggestions
            st.markdown(f"**{s.get('summary', '')}**")
            if s.get("priority_areas"):
                for area in s["priority_areas"]:
                    st.markdown(f"- 🔴 {area}")
            if s.get("suggestions"):
                for item in s["suggestions"]:
                    with st.expander(f"📌 {item.get('area', '')}"):
                        st.caption(f"当前问题：{item.get('current_issue', '')}")
                        st.caption(f"行动建议：{item.get('action', '')}")
                        st.caption(f"每周目标：{item.get('weekly_goal', '')}")
                        st.caption(f"预计提升：{item.get('estimated_improvement', '')}")
            if s.get("study_tips"):
                st.caption("学习技巧：")
                for tip in s["study_tips"]:
                    st.markdown(f"- {tip}")
            if s.get("motivation"):
                st.success(s["motivation"])

        # 学习计划 — 持久化显示
        st.subheader("📅 个性化学习计划")

        # 从 session 或用户进度中加载已有计划
        if "saved_study_plan" not in st.session_state:
            st.session_state.saved_study_plan = None

        if st.session_state.saved_study_plan is None:
            for record in user_progress:
                if record.get("activity") == "学习计划":
                    plan_data = record.get("data", {})
                    if isinstance(plan_data, dict) and plan_data.get("plan_text"):
                        st.session_state.saved_study_plan = plan_data["plan_text"]
                        break

        # 显示已有计划 + 重新生成按钮
        if st.session_state.saved_study_plan:
            st.markdown(st.session_state.saved_study_plan)
            col_a, col_b = st.columns([1, 4])
            with col_a:
                if st.button("🔄 重新生成"):
                    st.session_state.saved_study_plan = None
                    st.experimental_rerun()
        else:
            if st.button("📅 生成详细学习计划", type="primary"):
                with st.spinner("正在生成个性化学习计划..."):
                    try:
                        # 分析用户练习记录，获取平均分数
                        speaking_scores = []
                        writing_scores = []
                        for record in user_progress:
                            if "score" in record["data"]:
                                if "口语" in record["activity"]:
                                    speaking_scores.append(float(record["data"]["score"]))
                                elif "写作" in record["activity"]:
                                    writing_scores.append(float(record["data"]["score"]))
                        
                        # 计算平均分数作为当前水平参考
                        profile_level = _profile_overall_level(st.session_state.user_profile)
                        avg_speaking = sum(speaking_scores) / len(speaking_scores) if speaking_scores else st.session_state.user_profile.get("speaking_level", profile_level)
                        avg_writing = sum(writing_scores) / len(writing_scores) if writing_scores else st.session_state.user_profile.get("writing_level", profile_level)
                        
                        # 取平均作为当前综合水平
                        current_level = (avg_speaking + avg_writing) / 2 if (speaking_scores or writing_scores) else profile_level
                        
                        # 计算学习周数（基于距离考试时间）
                        try:
                            exam_date_str = st.session_state.user_profile.get('exam_date', '')
                            if exam_date_str and exam_date_str != '':
                                days_until_exam = (datetime.strptime(exam_date_str, '%Y-%m-%d') - datetime.now()).days
                                study_weeks = max(1, int(days_until_exam / 7))
                            else:
                                study_weeks = 12
                        except:
                            study_weeks = 12
                        
                        # 生成学习计划（AI 版本）
                        if st.session_state.tongyi_agent:
                            weak_areas = []
                            if speaking_scores and avg_speaking < st.session_state.user_profile.get("speaking_level", 6):
                                weak_areas.append("口语")
                            if writing_scores and avg_writing < st.session_state.user_profile.get("writing_level", 6):
                                weak_areas.append("写作")
                            if not weak_areas:
                                weak_areas = st.session_state.user_profile.get("weak_areas", ["口语", "写作"])

                            study_plan = st.session_state.tongyi_agent.generate_study_plan(
                                current_level=current_level,
                                target_score=st.session_state.user_profile["target_score"],
                                weak_areas=weak_areas,
                                weeks=study_weeks,
                                progress_records=user_progress,
                            )

                            st.session_state.saved_study_plan = study_plan
                            st.markdown(study_plan)

                            # 保存到进度
                            save_user_progress(
                                st.session_state.user_profile.get("user_id", "default_user"),
                                "学习计划",
                                {"plan_text": study_plan},
                            )
                        else:
                            st.error("请先在侧边栏配置 AI API Key")
                    except Exception as e:
                        st.error(f"生成学习计划时出错: {str(e)}")





# 主程序入口
if __name__ == "__main__":
    # 检查必要的环境变量
    if not st.session_state.dashscope_api_key:
        st.sidebar.error("请配置并保存AI API Key以使用全部功能")

    # 显示版本信息
    st.sidebar.markdown("---")
    st.sidebar.write("**版本信息**")
    st.sidebar.write("信达雅 v1.0")
    st.sidebar.write("支持通义千问、DeepSeek、OpenAI等模型")


    # 口语Part 3界面函数
    def _render_speaking_part3():
        st.write("**Part 3: 深入讨论**")

        st.info("💡 Part 3基于Part 2的话题进行深入讨论，考察分析能力和批判性思维")

        col1, col2 = st.columns(2)

        with col1:
            part2_topic = st.text_input(
                "Part 2话题",
                placeholder="输入Part 2的话题内容",
                help="这是Part 3讨论的基础"
            )

            discussion_type = st.selectbox(
                "讨论类型",
                ["社会影响", "发展趋势", "比较分析", "问题解决", "个人观点", "原因分析", "未来预测"]
            )

            if st.button("生成Part 3讨论题", type="primary") and part2_topic:
                with st.spinner("正在生成深入的讨论题目..."):
                    try:
                        result = st.session_state.tongyi_agent.practice_speaking_part3(
                            part2_topic=part2_topic,
                            discussion_type=discussion_type
                        )
                        st.session_state.current_speaking_question = parse_json_response(result)
                    except Exception as e:
                        st.error(f"生成讨论题时出错: {str(e)}")

        with col2:
            st.write("**Part 3特点：**")
            st.write("""
            - 4-5分钟讨论时间
            - 基于Part 2话题的深入探讨
            - 考察分析能力和批判性思维
            - 重点：逻辑性、深度、词汇多样性
            """)

            st.write("**回答技巧：**")
            st.write("""
            1. 明确表达个人观点
            2. 提供具体例子支持
            3. 从多角度分析问题
            4. 使用连接词体现逻辑
            5. 展现词汇和语法的丰富性
            """)

        # 显示讨论题目
        if "current_speaking_question" in st.session_state:
            question_data = st.session_state.current_speaking_question

            if "discussion_questions" in question_data:
                st.markdown("---")
                st.subheader("💭 讨论题目")

                for i, q in enumerate(question_data["discussion_questions"]):
                    with st.expander(f"讨论题 {i + 1}: {q.get('question', '')}"):
                        if "purpose" in q:
                            st.write(f"**考察目的:** {q['purpose']}")

                        if "depth_required" in q:
                            st.write(f"**要求深度:** {q['depth_required']}")

                        if "model_response" in q:
                            st.write("**参考回答:**")
                            st.write(q["model_response"])

                        # 用户回答区域
                        user_response = st.text_area(
                            f"你的观点 {i + 1}",
                            placeholder="在这里输入你的分析和观点...",
                            height=150,
                            key=f"part3_response_{i}"
                        )

                        if user_response and st.button(f"分析回答 {i + 1}", key=f"part3_feedback_{i}"):
                            with st.spinner("正在分析你的讨论回答..."):
                                try:
                                    feedback = st.session_state.tongyi_agent.get_speaking_feedback_direct(
                                        question=q["question"],
                                        user_response=user_response,
                                        target_score=st.session_state.user_profile["target_score"]
                                    )
                                    feedback_data = parse_json_response(feedback)
                                    st.session_state[f"part3_feedback_result_{i}"] = feedback_data
                                except Exception as e:
                                    st.error(f"分析回答时出错: {str(e)}")

                        fb_key = f"part3_feedback_result_{i}"
                        if fb_key in st.session_state and st.session_state[fb_key]:
                            _display_speaking_feedback(st.session_state[fb_key])

                # 显示分析角度和词汇
                if "analytical_angles" in question_data:
                    with st.expander("🔍 分析角度建议"):
                        st.write("**可用的分析角度:**")
                        for angle in question_data["analytical_angles"]:
                            st.write(f"• {angle}")

                if "extended_vocabulary" in question_data:
                    with st.expander("📚 扩展词汇"):
                        vocab_cols = st.columns(3)
                        vocab_list = question_data["extended_vocabulary"]
                        for i, word in enumerate(vocab_list):
                            vocab_cols[i % 3].code(word)
