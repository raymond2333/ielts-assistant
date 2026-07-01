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
    def get_speaking_feedback(self, question, user_response, target_score, reference_answer_note="无"):
        return self._get_feedback("Part 2", question, user_response, target_score, reference_answer_note)

    def get_speaking_feedback_direct(self, question, user_response, target_score, part="Part 1", reference_answer_note="无"):
        return self._get_feedback(part, question, user_response, target_score, reference_answer_note)

    def _get_feedback(self, part, question, user_response, target_score, reference_answer_note="无"):
        prompt = SPEAKING_FEEDBACK_SIMPLE_PROMPT.format(
            part=part,
            question=question,
            user_response=user_response,
            target_score=target_score,
            reference_answer_note=reference_answer_note or "无",
        )
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

    def generate_writing_ideas_with_chart(self, topic, chart_data, question, table_data=None):
        cd = chart_data or "无"
        td = table_data or "无"
        prompt = WRITING_IDEAS_WITH_CHART_PROMPT.format(
            topic=topic, chart_data=cd, table_data=td, question=question
        )
        return self.llm.invoke(prompt).content

    # ============================================================
    # 生成写作题目
    # ============================================================
    def generate_writing_topic(self, task_type, chart_type="柱状图", topic="教育"):
        if task_type == "Task 1":
            # 根据图表类型动态构建 prompt 的不同部分
            chart_types_with_data = ["柱状图", "线形图", "饼图"]
            if chart_type in chart_types_with_data:
                chart_specific_instructions = (
                    "4. 横轴标签（chart_labels）使用英文，根据话题使用实际语境对应的年份、月份或类别。例如：\n"
                    "   - 线形图/柱状图：Jan-Dec（月份）、2015-2023（年份）、Spring-Winter（季节）\n"
                    "   - 饼图：类别名（如年龄段、支出类别、能源类型等）\n"
                    "5. 必须同时输出 chart_data 数组（每个元素含 label 和 value），label 用英文\n"
                    "6. 数值范围应在 5-95 之间"
                )
                chart_specific_fields = (
                    "**chart_labels：** [\"Label1\", \"Label2\", \"Label3\", \"Label4\", \"Label5\", \"Label6\"]\n\n"
                    "**chart_data：** [{\"label\": \"Label1\", \"value\": 数值}, {\"label\": \"Label2\", \"value\": 数值}, ...]"
                )
            elif chart_type == "流程图":
                chart_specific_instructions = (
                    "4. 描述流程的各个步骤，确保步骤按实际顺序排列\n"
                    "5. 必须输出 chart_dot JSON 对象：包含 nodes（流程步骤英文名称列表，4-8 个步骤）和 edges（步骤连接关系，每个边用 [from_index, to_index] 表示序号索引）\n"
                    "6. 流程通常为线性步骤，可带有简单分支，如 [[0,1],[1,2],[2,3],[3,4]] 表示 5 个步骤依次连接"
                )
                chart_specific_fields = (
                    "**chart_dot：** {\"nodes\": [\"Raw materials harvested\", \"Transported to factory\", \"Sorted and cleaned\", \"Processed into products\", \"Packaged for distribution\"], \"edges\": [[0, 1], [1, 2], [2, 3], [3, 4]]}"
                )
            elif chart_type == "表格":
                chart_specific_instructions = (
                    "4. 设计一个包含多行多列的数据表格，第1列为类别/项目名称，后续列为不同时间段或不同类别的数值\n"
                    "5. 必须输出 table_data JSON 对象：headers（列标题英文列表）和 rows（数据行列表，每行为一个英文列表）\n"
                    "6. 表格应有 4-7 行数据、2-5 列，数值合理\n"
                    "7. 不需要输出 chart_labels 或 chart_data"
                )
                chart_specific_fields = (
                    "**table_data：** {\"headers\": [\"Category\", \"2018\", \"2019\", \"2020\"], \"rows\": [[\"Category A\", 45, 52, 61], [\"Category B\", 38, 41, 49], [\"Category C\", 55, 48, 42], [\"Category D\", 62, 58, 55]]}"
                )
            else:
                # 地图 — 不需要 chart_data，只出题目描述
                chart_specific_instructions = (
                    "4. 详细描述地图的内容，包括区域、方向、变化等信息\n"
                    "5. 不需要输出 chart_labels 或 chart_data"
                )
                chart_specific_fields = "**图表描述：** 详细的图表内容描述"

            prompt = GENERATE_WRITING_TOPIC_TASK1_PROMPT.format(
                chart_type=chart_type,
                topic=topic,
                chart_specific_instructions=chart_specific_instructions,
                chart_specific_fields=chart_specific_fields,
                output_rules=OUTPUT_RULES,
            )
        else:
            prompt = GENERATE_WRITING_TOPIC_TASK2_PROMPT.format(
                topic=topic,
                OUTPUT_RULES=OUTPUT_RULES,
            )
        return self.llm.invoke(prompt).content

    # ============================================================
    # 生成参考范文
    # ============================================================
    def generate_model_answer(self, task_type, topic, chart_type="", chart_data=None, table_data=None):
        cd = json.dumps(chart_data, ensure_ascii=False) if chart_data else "无"
        td = json.dumps(table_data, ensure_ascii=False) if table_data else "无"
        prompt = GENERATE_MODEL_ANSWER_PROMPT.format(
            task_type=task_type,
            topic=topic,
            chart_type=chart_type or "无",
            chart_data=cd,
            table_data=td,
        )
        return self.llm.invoke(prompt).content

    # ============================================================
    # 口语串题
    # ============================================================
    def link_speaking_themes(self, topics, main_theme, target_score):
        prompt = THEME_LINKING_PROMPT.format(topics=", ".join(topics), main_theme=main_theme)
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
