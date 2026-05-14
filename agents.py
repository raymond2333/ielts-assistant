import os
import json
from langchain_community.chat_models import ChatTongyi
from langchain_openai import ChatOpenAI
from prompts import *


class TongyiIELTSAssistant:
    def __init__(self, api_key, provider="tongyi", model=None, base_url=None):
        self.provider = provider
        self.model = model
        self.base_url = base_url
        self.llm = self._create_llm(api_key, provider, model, base_url)

    def _create_llm(self, api_key, provider, model=None, base_url=None):
        provider = (provider or "tongyi").lower()
        model_defaults = {
            "tongyi": "qwen-turbo",
            "deepseek": "deepseek-chat",
            "openai": "gpt-4o-mini",
            "custom": model or "gpt-4o-mini",
        }
        if provider == "tongyi":
            return ChatTongyi(model=model or model_defaults["tongyi"], dashscope_api_key=api_key, temperature=0.7)
        if provider == "deepseek":
            return ChatOpenAI(model=model or model_defaults["deepseek"], api_key=api_key, base_url=base_url or "https://api.deepseek.com", temperature=0.7)
        if provider == "openai":
            return ChatOpenAI(model=model or model_defaults["openai"], api_key=api_key, base_url=base_url or None, temperature=0.7)
        if provider == "custom":
            return ChatOpenAI(model=model_defaults["custom"], api_key=api_key, base_url=base_url, temperature=0.7)
        raise ValueError(f"不支持的AI供应商: {provider}")

    # ============================================================
    # 口语练习
    # ============================================================
    def practice_speaking_part1(self, topic, difficulty):
        prompt = SPEAKING_PART1_PROMPT.format(topic=topic, difficulty=difficulty)
        return self.llm.invoke(prompt).content

    def practice_speaking_part2(self, topic, cue_card_type):
        prompt = SPEAKING_PART2_PROMPT.format(topic=topic, cue_card_type=cue_card_type)
        return self.llm.invoke(prompt).content

    def practice_speaking_part3(self, part2_topic, discussion_type):
        prompt = SPEAKING_PART3_PROMPT.format(part2_topic=part2_topic, discussion_type=discussion_type)
        return self.llm.invoke(prompt).content

    # ============================================================
    # 口语反馈
    # ============================================================
    def get_speaking_feedback(self, question, user_response, target_score):
        return self._get_feedback("Part 2", question, user_response, target_score)

    def get_speaking_feedback_direct(self, question, user_response, target_score):
        return self._get_feedback("Part 1", question, user_response, target_score)

    def _get_feedback(self, part, question, user_response, target_score):
        prompt = SPEAKING_FEEDBACK_SIMPLE_PROMPT.format(part=part, question=question, user_response=user_response, target_score=target_score)
        return self.llm.invoke(prompt).content

    # ============================================================
    # 中文思路 → 英文口语答案
    # ============================================================
    def generate_answer_from_cn(self, question, chinese_answer):
        prompt = ANSWER_FROM_CN_PROMPT.format(question=question, chinese_answer=chinese_answer)
        return self.llm.invoke(prompt).content

    # ============================================================
    # 关键词生成口语答案
    # ============================================================
    def generate_answer_from_keywords(self, question, keywords, part="Part 2"):
        prompt = KEYWORD_ANSWER_PROMPT.format(question=question, keywords=keywords, part=part)
        return self.llm.invoke(prompt).content

    # ============================================================
    # 写作批改
    # ============================================================
    def correct_writing_task1(self, task_type, essay_content, target_score):
        prompt = WRITING_TASK1_CORRECTION_PROMPT.format(task_type=task_type, essay_content=essay_content, target_score=target_score)
        return self.llm.invoke(prompt).content

    def correct_writing_task2(self, topic, essay_type, essay_content, target_score):
        prompt = WRITING_TASK2_CORRECTION_PROMPT.format(topic=topic, essay_type=essay_type, essay_content=essay_content, target_score=target_score)
        return self.llm.invoke(prompt).content

    # ============================================================
    # 写作思路互动
    # ============================================================
    def generate_writing_ideas(self, topic, question):
        prompt = WRITING_IDEAS_OLD_PROMPT.format(topic=topic, question=question)
        return self.llm.invoke(prompt).content

    def generate_writing_ideas_with_chart(self, topic, chart_data, question):
        prompt = WRITING_IDEAS_WITH_CHART_PROMPT.format(topic=topic, chart_data=chart_data or "无", question=question)
        return self.llm.invoke(prompt).content

    # ============================================================
    # 生成写作题目
    # ============================================================
    def generate_writing_topic(self, task_type):
        prompt_template = GENERATE_WRITING_TOPIC_PROMPT_MAP.get(task_type, GENERATE_WRITING_TOPIC_TASK2_PROMPT)
        return self.llm.invoke(prompt_template).content

    # ============================================================
    # 生成参考范文
    # ============================================================
    def generate_model_answer(self, task_type, topic):
        prompt = GENERATE_MODEL_ANSWER_PROMPT.format(task_type=task_type, topic=topic)
        return self.llm.invoke(prompt).content

    # ============================================================
    # 口语串题
    # ============================================================
    def link_speaking_themes(self, topics, main_theme, target_score):
        prompt = THEME_LINKING_PROMPT.format(topics=", ".join(topics), main_theme=main_theme, target_score=target_score)
        return self.llm.invoke(prompt).content

    def expand_topic(self, topic, expansion_type):
        prompt = TOPIC_EXPANSION_PROMPT.format(topic=topic, expansion_type=expansion_type)
        return self.llm.invoke(prompt).content

    # ============================================================
    # 词汇查询
    # ============================================================
    def explain_word(self, word):
        prompt = WORD_EXPLANATION_PROMPT_FULL.format(word=word)
        return self.llm.invoke(prompt).content

    # ============================================================
    # 音频转写
    # ============================================================
    def transcribe_audio(self):
        return self.llm.invoke(AUDIO_TRANSCRIPT_PROMPT).content

    # ============================================================
    # 提升建议（根据学习记录生成）
    # ============================================================
    def generate_improvement_suggestions(self, progress_records, weak_areas, target_score, current_level):
        history_summary = []
        for r in progress_records[-15:]:
            activity = r.get("activity", "")
            score = r.get("score") or r.get("data", {}).get("score", "")
            topic = r.get("data", {}).get("topic", "")
            entry = f"- {activity}"
            if topic:
                entry += f" (话题: {topic})"
            if score:
                entry += f" 得分: {score}"
            history_summary.append(entry)

        gap = target_score - current_level
        weak_areas_text = ", ".join(weak_areas) if weak_areas else "未指定"
        history_text = "\n".join(history_summary) if history_summary else "暂无训练记录"
        prompt = IMPROVEMENT_SUGGESTIONS_PROMPT.format(
            current_level=current_level,
            target_score=target_score,
            weak_areas_text=weak_areas_text,
            gap=f"{gap:.1f}",
            history_text=history_text,
            output_rules=OUTPUT_RULES,
        )
        return self.llm.invoke(prompt).content

    def generate_study_plan(self, current_level, target_score, weak_areas, weeks, progress_records):
        history_summary = []
        for r in progress_records[-15:]:
            activity = r.get("activity", "")
            score = r.get("score") or r.get("data", {}).get("score", "")
            topic = r.get("data", {}).get("topic", "")
            entry = f"- {activity}"
            if topic:
                entry += f" (话题: {topic})"
            if score:
                entry += f" 得分: {score}"
            history_summary.append(entry)

        gap = target_score - current_level
        weak_areas_text = ", ".join(weak_areas) if weak_areas else "未指定"
        history_text = "\n".join(history_summary) if history_summary else "暂无训练记录"
        prompt = STUDY_PLAN_PROMPT.format(
            current_level=current_level,
            target_score=target_score,
            weak_areas_text=weak_areas_text,
            gap=f"{gap:.1f}",
            weeks=weeks,
            history_text=history_text,
        )
        return self.llm.invoke(prompt).content
