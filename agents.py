import os
import json
from langchain_community.chat_models import ChatTongyi
from langchain_openai import ChatOpenAI
from prompts import *


class TongyiIELTSAssistant:
    def __init__(self, api_key, provider="tongyi", model=None, base_url=None):
        self.provider = provider
        self.requested_model = model
        self.base_url = base_url
        self.model = self._safe_chat_model(provider, model)
        self.used_model_fallback = bool(model and self.model != model)
        self.llm = self._create_llm(api_key, provider, self.model, base_url)

    def _safe_chat_model(self, provider, model=None):
        provider = (provider or "tongyi").lower()
        model_defaults = {
            "tongyi": "qwen-turbo",
            "deepseek": "deepseek-chat",
            "openai": "gpt-4o-mini",
            "siliconflow": "Qwen/Qwen2.5-72B-Instruct",
            "moonshot": "moonshot-v1-8k",
            "zhipu": "glm-4-flash",
            "volcengine": "doubao-1-5-lite-32k-250115",
            "xunfei": "generalv3.5",
            "mimo": "mimo-v2.5-pro",
            "custom": "gpt-4o-mini",
        }
        selected = (model or "").strip()
        non_chat_markers = [
            "tts", "asr", "speech", "audio", "whisper", "transcribe",
            "voice", "embedding", "rerank", "vision-only",
        ]
        if selected and not any(marker in selected.lower() for marker in non_chat_markers):
            return selected
        return model_defaults.get(provider, selected or "gpt-4o-mini")

    def _create_llm(self, api_key, provider, model=None, base_url=None):
        provider = (provider or "tongyi").lower()
        model_defaults = {
            "tongyi": "qwen-turbo",
            "deepseek": "deepseek-chat",
            "openai": "gpt-4o-mini",
            "siliconflow": "Qwen/Qwen2.5-72B-Instruct",
            "moonshot": "moonshot-v1-8k",
            "zhipu": "glm-4-flash",
            "volcengine": "doubao-1-5-lite-32k-250115",
            "xunfei": "generalv3.5",
            "mimo": "mimo-v2.5-pro",
            "custom": model or "gpt-4o-mini",
        }
        if provider == "tongyi":
            return ChatTongyi(model=model or model_defaults["tongyi"], dashscope_api_key=api_key, temperature=0.7)
        if provider == "deepseek":
            return ChatOpenAI(model=model or model_defaults["deepseek"], api_key=api_key, base_url=base_url or "https://api.deepseek.com", temperature=0.7)
        if provider == "openai":
            return ChatOpenAI(model=model or model_defaults["openai"], api_key=api_key, base_url=base_url or None, temperature=0.7)
        if provider == "siliconflow":
            return ChatOpenAI(model=model or model_defaults["siliconflow"], api_key=api_key, base_url=base_url or "https://api.siliconflow.cn/v1", temperature=0.7)
        if provider == "moonshot":
            return ChatOpenAI(model=model or model_defaults["moonshot"], api_key=api_key, base_url=base_url or "https://api.moonshot.cn/v1", temperature=0.7)
        if provider == "zhipu":
            return ChatOpenAI(model=model or model_defaults["zhipu"], api_key=api_key, base_url=base_url or "https://open.bigmodel.cn/api/paas/v4", temperature=0.7)
        if provider == "volcengine":
            return ChatOpenAI(model=model or model_defaults["volcengine"], api_key=api_key, base_url=base_url or "https://ark.cn-beijing.volces.com/api/v3", temperature=0.7)
        if provider == "xunfei":
            return ChatOpenAI(model=model or model_defaults["xunfei"], api_key=api_key, base_url=base_url or "https://spark-api-open.xf-yun.com/v1", temperature=0.7)
        if provider == "mimo":
            return ChatOpenAI(model=model or model_defaults["mimo"], api_key=api_key, base_url=base_url or "https://api.xiaomimimo.com/v1", temperature=0.7)
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
    def correct_writing_task1(self, task_type, essay_content, target_score, topic=""):
        prompt = WRITING_TASK1_CORRECTION_PROMPT.format(task_type=task_type, topic=topic or "未提供", essay_content=essay_content, target_score=target_score)
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
        if task_type == "Task 1":
            prompt = GENERATE_MODEL_ANSWER_TASK1_PROMPT.format(
                topic=topic,
                chart_type=chart_type or "无",
                chart_data=cd,
                table_data=td,
            )
        else:
            prompt = GENERATE_MODEL_ANSWER_TASK2_PROMPT.format(topic=topic)
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
    def _progress_record_summary(self, record):
        data = record.get("data", {}) if isinstance(record, dict) else {}
        if not isinstance(data, dict):
            data = {}
        result_data = data.get("result_data", {})
        if not isinstance(result_data, dict):
            result_data = {}

        activity = record.get("activity", "") or data.get("mode", "训练")
        timestamp = (record.get("timestamp") or "")[:16]
        score = (
            result_data.get("overall_score")
            or data.get("score")
            or record.get("score")
            or ""
        )
        topic = (
            data.get("question")
            or data.get("topic")
            or result_data.get("question")
            or result_data.get("topic")
            or ""
        )

        dimensions = []
        breakdown = result_data.get("breakdown")
        if isinstance(breakdown, dict):
            for key, value in breakdown.items():
                if isinstance(value, dict) and value.get("score") not in (None, ""):
                    dimensions.append(f"{key}: {value.get('score')}")
        for key in [
            "task_achievement",
            "task_response",
            "coherence_cohesion",
            "lexical_resource",
            "grammatical_range_accuracy",
        ]:
            value = result_data.get(key)
            if isinstance(value, dict) and value.get("score") not in (None, ""):
                dimensions.append(f"{key}: {value.get('score')}")

        feedback_bits = []
        for key in ["practice_recommendations", "improvements", "suggestions", "strengths"]:
            value = result_data.get(key)
            if isinstance(value, list):
                feedback_bits.extend(str(item) for item in value[:2])
            elif isinstance(value, str):
                feedback_bits.append(value)
        if not feedback_bits:
            for key in ["band_description", "overall_feedback", "comments"]:
                value = result_data.get(key)
                if isinstance(value, str) and value.strip():
                    feedback_bits.append(value.strip())

        answer = data.get("transcript") or data.get("user_response") or data.get("essay_content") or ""
        if answer:
            answer = str(answer).replace("\n", " ")[:110]

        parts = [f"- {timestamp} {activity}".strip()]
        if score not in (None, ""):
            parts.append(f"得分 {score}")
        if topic:
            parts.append(f"题目/话题：{str(topic).replace(chr(10), ' ')[:130]}")
        if dimensions:
            parts.append("维度分：" + "；".join(dimensions[:4]))
        if feedback_bits:
            parts.append("反馈重点：" + "；".join(str(item).replace("\n", " ")[:80] for item in feedback_bits[:3]))
        if answer:
            parts.append(f"学生作答摘录：{answer}")
        return " | ".join(parts)

    def _progress_history_text(self, progress_records, limit=15):
        summaries = []
        for record in progress_records[-limit:]:
            if not isinstance(record, dict):
                continue
            activity = record.get("activity", "")
            if activity in {"个性化学习计划", "重点提升建议"}:
                continue
            summary = self._progress_record_summary(record)
            if summary:
                summaries.append(summary)
        return "\n".join(summaries) if summaries else "暂无训练记录"

    @staticmethod
    def _round_ielts(value):
        try:
            return max(0.0, min(9.0, round(float(value) * 2) / 2))
        except (TypeError, ValueError):
            return 0.0

    def generate_improvement_suggestions(self, progress_records, weak_areas, target_score, current_level):
        gap = self._round_ielts(max(0.0, float(target_score) - float(current_level)))
        weak_areas_text = ", ".join(weak_areas) if weak_areas else "未指定"
        history_text = self._progress_history_text(progress_records)
        prompt = IMPROVEMENT_SUGGESTIONS_PROMPT.format(
            current_level=f"{self._round_ielts(current_level):.1f}",
            target_score=f"{self._round_ielts(target_score):.1f}",
            weak_areas_text=weak_areas_text,
            gap=f"{gap:.1f}",
            history_text=history_text,
            output_rules=OUTPUT_RULES,
        )
        return self.llm.invoke(prompt).content

    def generate_study_plan(
        self,
        current_level,
        target_score,
        weak_areas,
        weeks,
        progress_records,
        exam_date="",
        days_until_exam=None,
    ):
        gap = self._round_ielts(max(0.0, float(target_score) - float(current_level)))
        weak_areas_text = ", ".join(weak_areas) if weak_areas else "未指定"
        history_text = self._progress_history_text(progress_records)
        exam_date_text = exam_date or "未设置"
        days_until_exam_text = f"{days_until_exam} 天" if days_until_exam not in (None, "") else "未设置"
        prompt = STUDY_PLAN_PROMPT.format(
            current_level=f"{self._round_ielts(current_level):.1f}",
            target_score=f"{self._round_ielts(target_score):.1f}",
            weak_areas_text=weak_areas_text,
            gap=f"{gap:.1f}",
            weeks=weeks,
            exam_date_text=exam_date_text,
            days_until_exam_text=days_until_exam_text,
            history_text=history_text,
        )
        return self.llm.invoke(prompt).content
