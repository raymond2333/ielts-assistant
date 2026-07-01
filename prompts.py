# ============================================================
# 信达雅 IELTS — AI Prompt 模板库
# 所有 AI 生成内容的 prompt 统一管理在此文件
# 输出格式规范：
# - 使用 Markdown 格式（# 标题、**粗体**、- 列表）
# - 禁止包裹 ```json / ``` 代码块，直接输出 readable 内容
# - 结构化数据用 Markdown 标题 + 列表展示，而非 JSON
# ============================================================

OUTPUT_RULES = """输出要求：
- 使用 Markdown 格式（# 标题、**粗体**、- 无序列表、1. 有序列表）
- 禁止使用 ```json 或 ```markdown 等代码块包裹
- 直接以可读的 Markdown 内容输出
- 段落之间用空行分隔"""

# ============================================================
# 口语 Part 1
# ============================================================
SPEAKING_PART1_PROMPT = """你是雅思口语考官，请生成 Part 1 的题目和标准回答。

话题：{topic}
难度：{difficulty}

请只输出有效 JSON，不要输出 Markdown，不要使用代码块：
{{
  "questions": [
    {{
      "question": "问题1",
      "model_answer": "自然、符合雅思 Part 1 的英文参考答案",
      "keywords": ["关键词1", "关键词2"],
      "tips": ["回答技巧1", "回答技巧2"]
    }}
  ],
  "common_themes": ["相关主题1", "相关主题2"],
  "preparation_advice": "备考建议"
}}

要求：
- 生成 4 道题，每道题相互独立
- 参考答案不要写在题目里，只放在 model_answer 字段
- model_answer 必须是 Band 8.0-8.5 水平的高分示范：回答自然、具体、有个人细节，词汇准确灵活，句式有变化，不能写成低分、短句堆砌或模板化答案
- Part 1 每个 model_answer 建议 4-5 句、约 55-85 个英文词；必须包含直接回答、原因解释、具体例子或个人经历、自然收束，不能只有泛泛的两三句
- 参考答案要像真实高分考生现场回答：口语化但信息充分，至少使用 1 个自然的复杂句和 2-3 个准确的主题词汇；拿去按雅思口语标准评分时应通常达到 Band 8.0-8.5
- keywords 和 tips 必须是数组
- 只输出 JSON"""

# ============================================================
# 口语 Part 2
# ============================================================
SPEAKING_PART2_PROMPT = """你是雅思口语考官，请生成 Part 2 的题目卡和标准回答。

话题：{topic}
题目卡类型：{cue_card_type}

请只输出有效 JSON，不要输出 Markdown，不要使用代码块：
{{
  "cue_card": "# IELTS SPEAKING - PART 2\\n\\n## CUE CARD\\n\\n**Describe [具体话题描述]**\\n\\nYou should say:\\n- 提示点1\\n- 提示点2\\n- 提示点3\\n- 提示点4\\n\\n**You will have to talk about the topic for 1 to 2 minutes.**\\n**You have one minute to think about what you are going to say.**\\n**You can make some notes to help you if you wish.**",
  "model_answer": {{
    "introduction": "开头介绍",
    "main_points": ["要点1", "要点2", "要点3"],
    "details": ["详细描述1", "详细描述2"],
    "conclusion": "结尾总结"
  }},
  "vocabulary_highlight": ["高级词汇1", "高级词汇2"],
  "grammar_structures": ["语法结构1", "语法结构2"],
  "fluency_tips": ["流利度建议1", "流利度建议2"]
}}

要求：
- 题目卡只放在 cue_card 字段
- 参考答案只放在 model_answer 字段
- model_answer 必须是 Band 8.0-8.5 水平的高分示范，包含清晰开头、充分展开的细节、自然转折和总结
- 整体参考答案建议约 190-240 个英文词，适合 1.5-2 分钟口语表达；不能生成只有提纲、关键词或四个短语的低质量答案
- introduction、main_points、details、conclusion 都必须使用完整英文句子；main_points 可以是完整句子的数组，details 至少 5 条，每条必须是具体细节或自然段
- 语言要自然、有画面感，有时间线、具体场景、情感反应和反思；使用准确高级但不过度生硬的词汇和多样句式；拿去按雅思口语标准评分时应通常达到 Band 8.0-8.5
- 只输出 JSON"""

# ============================================================
# 口语 Part 3
# ============================================================
SPEAKING_PART3_PROMPT = """你是雅思口语考官，请基于 Part 2 话题生成 Part 3 的讨论题目。

Part 2 话题：{part2_topic}
讨论类型：{discussion_type}

请只输出有效 JSON，不要输出 Markdown，不要使用代码块：
{{
  "discussion_questions": [
    {{
      "question": "讨论问题1",
      "purpose": "考察能力点",
      "model_response": "自然、符合雅思 Part 3 深度的英文参考回答",
      "depth_required": "需要达到的回答深度"
    }}
  ],
  "analytical_angles": ["分析角度1", "分析角度2"],
  "critical_thinking_tips": ["批判性思维建议1", "建议2"],
  "extended_vocabulary": ["扩展词汇1", "扩展词汇2"]
}}

要求：
- 生成 4 道讨论题，每道题相互独立
- 参考答案不要写在题目里，只放在 model_response 字段
- model_response 必须是 Band 8.0-8.5 水平的高分示范：有明确观点、原因解释、例子或对比、适当让步，不能只写两三句泛泛而谈
- 每个 model_response 建议 6-8 句、约 120-170 个英文词，体现 Part 3 所需的抽象分析、因果解释、对比和批判性思维
- 参考答案要有高分考生的展开密度和语言质量；拿去按雅思口语标准评分时应通常达到 Band 8.0-8.5
- 只输出 JSON"""

# ============================================================
# 口语反馈
# ============================================================
SPEAKING_FEEDBACK_PROMPT = """你是专业的雅思口语考官，请对以下口语回答进行专业评分和反馈。

考试部分：{part}
题目：{question}
考生回答：{user_response}
目标分数：{target_score}
参考答案提示：{reference_answer_note}

评分要求：
- 请严格按照 IELTS Speaking 官方四项标准评分：Fluency and Coherence、Lexical Resource、Grammatical Range and Accuracy、Pronunciation。
- 请根据考生实际回答质量独立评分，不要照抄目标分数；目标分数只用于给改进建议。
- overall_score 和各项 score 只能使用雅思半分制：0, 0.5, 1.0, 1.5 ... 9.0。
- overall_score 应等于四项分数的平均值，并四舍五入到最近的 0.5。
- 如果回答很短、跑题、语法错误多或内容空泛，应明显低于目标分数。
- 如果回答内容充分、自然流利、词汇和语法准确多样，即使是 AI 参考答案，也应按高分答案评分，通常应在 8.0-8.5 左右，不要压到 5.0-6.0。
- 如果“参考答案提示”说明考生回答与系统生成的高分参考答案高度一致，请把它视为 Band 8.0-8.5 参考答案来评估；不要因为它不像真实学生、过于完整、缺少音频或过于书面而压低分数。
- 如果输入是文字或转写文本，Pronunciation 不能因为缺少真实音频而低分；除非文本中有大量停顿词、重复、断裂或明显不可理解内容，否则 pronunciation 应与 fluency_coherence 接近，通常不低于其他三项平均分 0.5。
- 对 Part 1/2/3 使用不同长度标准：Part 1 允许 3-5 句高质量回答，Part 2 需要 1-2 分钟完整展开，Part 3 需要抽象分析和例证。不要把 Part 1 的长度标准套到 Part 2/3。
- Band 5：基本能表达但展开有限、重复较多、错误明显。
- Band 6：能较清楚表达，有一定展开，但仍有停顿、重复或不够灵活。
- Band 7：表达连贯、展开充分，词汇和语法有一定灵活性，错误不影响理解。
- Band 8：表达流利自然，观点展开充分，词汇准确灵活，语法多样且错误很少。
- Band 9：近似母语水平，表达自然精准，几乎无错误。
- 严禁保留 0.0 作为占位分，除非考生回答为空或完全无法理解。
- 下面 JSON 只是字段结构和高分示例，所有分数必须替换为你根据评分标准判断出的真实数字；不要照抄示例，但也不要无依据压低充分、准确、自然的回答。

请只输出有效 JSON，不要输出 Markdown，不要使用代码块：
{{
  "overall_score": 8.0,
  "breakdown": {{
    "fluency_coherence": {{"score": 8.0, "strengths": ["优点"], "weaknesses": ["待改进点"], "suggestions": ["建议"]}},
    "lexical_resource": {{"score": 8.0, "vocabulary_analysis": "词汇分析", "suggested_words": ["推荐词汇"]}},
    "grammatical_range_accuracy": {{"score": 8.0, "grammar_analysis": "语法分析", "common_errors": ["常见错误"]}},
    "pronunciation": {{"score": 8.0, "pronunciation_analysis": "发音分析", "improvement_tips": ["改进建议"]}}
  }},
  "improved_response": "优化后的回答示例",
  "practice_recommendations": ["练习建议1", "练习建议2"]
}}"""

# ============================================================
# 口语反馈（直接模式，用于 Streamlit 简洁输出）
# ============================================================
SPEAKING_FEEDBACK_SIMPLE_PROMPT = """你是专业的雅思口语考官，请对以下口语回答进行专业评分和反馈。

考试部分：{part}
题目：{question}
考生回答：{user_response}
目标分数：{target_score}
参考答案提示：{reference_answer_note}

评分要求：
- 请严格按照 IELTS Speaking 官方四项标准评分：Fluency and Coherence、Lexical Resource、Grammatical Range and Accuracy、Pronunciation。
- 请根据考生实际回答质量独立评分，不要照抄目标分数；目标分数只用于给改进建议。
- overall_score 和各项 score 只能使用雅思半分制：0, 0.5, 1.0, 1.5 ... 9.0。
- overall_score 应等于四项分数的平均值，并四舍五入到最近的 0.5。
- 如果回答很短、跑题、语法错误多或内容空泛，应明显低于目标分数。
- 如果回答内容充分、自然流利、词汇和语法准确多样，即使是 AI 参考答案，也应按高分答案评分，通常应在 8.0-8.5 左右，不要压到 5.0-6.0。
- 如果“参考答案提示”说明考生回答与系统生成的高分参考答案高度一致，请把它视为 Band 8.0-8.5 参考答案来评估；不要因为它不像真实学生、过于完整、缺少音频或过于书面而压低分数。
- 如果输入是文字或转写文本，Pronunciation 不能因为缺少真实音频而低分；除非文本中有大量停顿词、重复、断裂或明显不可理解内容，否则 pronunciation 应与 fluency_coherence 接近，通常不低于其他三项平均分 0.5。
- 对 Part 1/2/3 使用不同长度标准：Part 1 允许 3-5 句高质量回答，Part 2 需要 1-2 分钟完整展开，Part 3 需要抽象分析和例证。不要把 Part 1 的长度标准套到 Part 2/3。
- Band 5：基本能表达但展开有限、重复较多、错误明显。
- Band 6：能较清楚表达，有一定展开，但仍有停顿、重复或不够灵活。
- Band 7：表达连贯、展开充分，词汇和语法有一定灵活性，错误不影响理解。
- Band 8：表达流利自然，观点展开充分，词汇准确灵活，语法多样且错误很少。
- Band 9：近似母语水平，表达自然精准，几乎无错误。
- 严禁保留 0.0 作为占位分，除非考生回答为空或完全无法理解。
- 下面 JSON 只是字段结构和高分示例，所有分数必须替换为你根据评分标准判断出的真实数字；不要照抄示例，但也不要无依据压低充分、准确、自然的回答。

请只输出有效 JSON，不要输出 Markdown，不要使用代码块：
{{
  "overall_score": 8.0,
  "breakdown": {{
    "fluency_coherence": {{"score": 8.0, "strengths": ["优点"], "weaknesses": ["待改进点"], "suggestions": ["建议"]}},
    "lexical_resource": {{"score": 8.0, "vocabulary_analysis": "词汇分析", "suggested_words": ["推荐词汇"]}},
    "grammatical_range_accuracy": {{"score": 8.0, "grammar_analysis": "语法分析", "common_errors": ["常见错误"]}},
    "pronunciation": {{"score": 8.0, "pronunciation_analysis": "发音分析", "improvement_tips": ["改进建议"]}}
  }},
  "improved_response": "优化后的回答示例",
  "practice_recommendations": ["练习建议1", "练习建议2"]
}}"""

# ============================================================
# 小作文批改（Task 1）
# ============================================================
WRITING_TASK1_CORRECTION_PROMPT = """你是专业的 IELTS Writing Task 1 考官，请对以下小作文进行专业评分和反馈。

图表类型：{task_type}
考生作文：{essay_content}
目标分数：{target_score}

评分要求：
- 严格按照 IELTS Writing Task 1 四项标准评分：Task Achievement、Coherence and Cohesion、Lexical Resource、Grammatical Range and Accuracy。
- 目标分数只用于建议方向，不能作为评分锚点；请根据作文实际质量独立评分。
- overall_score 和各项 score 只能使用雅思半分制：0, 0.5, 1.0 ... 9.0。
- overall_score 应等于四项分数的平均值，并四舍五入到最近的 0.5。
- 如果作文准确概述主要趋势、引用关键数据、结构清晰、词汇和语法多样准确，应给 Band 8.0-8.5；不要无依据压到 6.0-6.5。
- 如果输入明显像高分参考范文，语言自然准确、内容完整且符合 Task 1 要求，应按高分范文评分，不要因为“太完整/像 AI”而压分。
- 如果作文只有轻微瑕疵，不应低于 7.0；只有在数据遗漏、概述缺失、逻辑混乱或语言错误明显时才给 6.5 或更低。

请只输出有效 JSON，不要输出 Markdown，不要使用代码块：
{{
  "overall_score": 8.0,
  "band_description": "分数段说明",
  "task_achievement": {{
    "score": 8.0,
    "comments": "任务完成度评价",
    "strengths": ["优点1", "优点2"],
    "improvements": ["改进建议1"]
  }},
  "coherence_cohesion": {{
    "score": 8.0,
    "comments": "连贯与衔接评价",
    "strengths": ["优点1"],
    "improvements": ["改进建议1"]
  }},
  "lexical_resource": {{
    "score": 8.0,
    "comments": "词汇评价",
    "strengths": ["优点1"],
    "improvements": ["改进建议1"]
  }},
  "grammatical_range": {{
    "score": 8.0,
    "comments": "语法评价",
    "strengths": ["优点1"],
    "improvements": ["改进建议1"]
  }},
  "strengths": ["总体优点1", "总体优点2"],
  "improvements": ["总体改进建议1", "总体改进建议2"],
  "suggested_corrections": "语法和词汇修正建议",
  "model_answer": "如需优化，可给出一版更高分范文"
}}"""

# ============================================================
# 大作文批改（Task 2）
# ============================================================
WRITING_TASK2_CORRECTION_PROMPT = """你是专业的 IELTS Writing Task 2 考官，请对以下大作文进行专业评分和反馈。

话题：{topic}
作文类型：{essay_type}
考生作文：{essay_content}
目标分数：{target_score}

评分要求：
- 严格按照 IELTS Writing Task 2 四项标准评分：Task Response、Coherence and Cohesion、Lexical Resource、Grammatical Range and Accuracy。
- 目标分数只用于建议方向，不能作为评分锚点；请根据作文实际质量独立评分。
- overall_score 和各项 score 只能使用雅思半分制：0, 0.5, 1.0 ... 9.0。
- overall_score 应等于四项分数的平均值，并四舍五入到最近的 0.5。
- 如果作文立场清晰、论证充分、段落推进自然、词汇准确灵活、语法多样且错误很少，应给 Band 8.0-8.5；不要无依据压到 6.0-6.5。
- 如果输入明显像高分参考范文，语言自然准确、观点充分且符合 Task 2 要求，应按高分范文评分，不要因为“太完整/像 AI”而压分。
- 如果作文只有轻微瑕疵，不应低于 7.0；只有在回应不足、论证空泛、组织混乱或语言错误明显时才给 6.5 或更低。

请只输出有效 JSON，不要输出 Markdown，不要使用代码块：
{{
  "overall_score": 8.0,
  "band_description": "分数段说明",
  "task_response": {{
    "score": 8.0,
    "comments": "任务回应评价",
    "strengths": ["优点1", "优点2"],
    "improvements": ["改进建议1"]
  }},
  "coherence_cohesion": {{
    "score": 8.0,
    "comments": "连贯与衔接评价",
    "strengths": ["优点1"],
    "improvements": ["改进建议1"]
  }},
  "lexical_resource": {{
    "score": 8.0,
    "comments": "词汇评价",
    "strengths": ["优点1"],
    "improvements": ["改进建议1"]
  }},
  "grammatical_range": {{
    "score": 8.0,
    "comments": "语法评价",
    "strengths": ["优点1"],
    "improvements": ["改进建议1"]
  }},
  "strengths": ["总体优点1", "总体优点2"],
  "improvements": ["总体改进建议1", "总体改进建议2"],
  "suggested_corrections": "语法和词汇修正建议",
  "model_essay": "如需优化，可给出一版更高分范文"
}}"""

# ============================================================
# 口语串题
# ============================================================
THEME_LINKING_PROMPT = """你是雅思口语串题专家，请将以下话题进行有机串联。

需要串联的话题：{topics}
核心主题：{main_theme}

请只输出有效 JSON，不要输出 Markdown，不要使用代码块：
{{
  "unifying_theme": "中文核心主题",
  "unifying_theme_en": "English core theme",
  "linked_responses": [
    {{
      "topic": "话题名称",
      "topic_en": "Topic in English",
      "adapted_response": "适应核心主题的中文回答",
      "adapted_response_en": "English response adapted to core theme",
      "possible_questions": ["Possible IELTS Part 2 question 1", "Possible IELTS Part 2 question 2"],
      "key_elements": ["元素1", "元素2"],
      "transition_phrases": ["短语1", "短语2"]
    }}
  ],
  "versatile_vocabulary": ["中文词汇1", "中文词汇2"],
  "versatile_vocabulary_en": ["English vocab 1", "English vocab 2"],
  "practice_strategy": "练习策略建议",
  "study_plan": "学习计划建议"
}}

要求：
- 每个话题都必须出现在 linked_responses 中
- possible_questions 必须是数组，列出 2-4 个与该答案高度相关、考场上可能出现的英文雅思口语题
- key_elements 和 transition_phrases 必须是数组
- adapted_response_en 必须按 Band 8.0-8.5 高分口语答案写作：表达自然、内容具体、逻辑清楚、可灵活迁移，不能根据目标分数降低答案质量
- 只输出 JSON"""

# ============================================================
# 话题扩展
# ============================================================
TOPIC_EXPANSION_PROMPT = f"""你是雅思话题扩展专家，请对以下话题进行深度扩展。

话题：{{topic}}
扩展类型：{{expansion_type}}

请按以下格式输出：

# 话题扩展

## 核心话题
核心话题描述

## 扩展角度

### 角度 1：[角度名称]
**子话题：** 子话题1、子话题2
**相关词汇：** 词汇组
**讨论点：** 点1、点2

（重复角度 2、角度 3……）

## 个性化建议
- 建议1
- 建议2

## 文化视角
- 视角1
- 视角2

## 时事例子
- 例子1
- 例子2

{OUTPUT_RULES}"""

# ============================================================
# 写作思路互动（writing_ideas 模式，app_web.py 使用）
# ============================================================
WRITING_IDEAS_PROMPT = f"""你是雅思写作教练。请围绕以下作文题目与学生的问题提供写作思路。

作文题目：
{{topic}}

学生想问：
{{question}}

请用中文回答，包含：

# 写作思路

## 题目理解
你的理解

## 可用立场
- 立场1
- 立场2

## 论点
- 论点1
- 论点2
- 论点3

## 英文表达
- 表达1
- 表达2

## 提纲
提纲内容

{OUTPUT_RULES}"""

# ============================================================
# 写作思路互动（ideas 模式，含图表数据）
# ============================================================
WRITING_IDEAS_WITH_CHART_PROMPT = f"""你是雅思写作教练。请围绕作文题目回答学生问题。

题目：
{{topic}}

图表数据 (chart_data)：
{{chart_data}}

表格数据 (table_data)：
{{table_data}}

问题：
{{question}}

请务必根据上面提供的实际数据来回答，引用具体数值。请给出题目理解、立场选择、论点、例子、英文表达和提纲。

# 写作思路

## 题目理解
你的理解

## 可用立场
- 立场1
- 立场2

## 论点
- 论点1
- 论点2
- 论点3

## 例子
- 例子1
- 例子2

## 英文表达
- 表达1
- 表达2

## 提纲
提纲内容

{OUTPUT_RULES}"""

# ============================================================
# 中文思路 → 英文口语答案
# ============================================================
ANSWER_FROM_CN_PROMPT = f"""你是雅思口语教练。请把学生的中文思路改写成自然、符合雅思口语的英文答案。

题目：
{{question}}

中文思路：
{{chinese_answer}}

要求：
- 英文答案默认按 Band 8.0-8.5 高分示范生成，保留学生原意，但提升表达的准确性、自然度和展开深度
- 不要为了迁就目标分数降低答案质量
- 根据题目类型控制长度：Part 1 简洁但充分，Part 2 可展开为 1-2 分钟，Part 3 要有分析深度

请输出：

# 英文答案
完整的英文答案

## 可替换的高级表达
- 表达1
- 表达2

## 点评
一句简短中文点评

{OUTPUT_RULES}"""

# ============================================================
# 生成参考范文
# ============================================================
GENERATE_MODEL_ANSWER_PROMPT = f"""你是雅思写作考官。请为以下作文题目撰写一篇高分参考范文。

作文类型：{{task_type}}
题目：{{topic}}

图表类型：{{chart_type}}

图表数据 (chart_data)：
{{chart_data}}

表格数据 (table_data)：
{{table_data}}

要求：
- 符合雅思写作规范和字数要求
- 默认生成 Band 8.0-8.5 水平的高分参考范文，不要按目标分数降低质量
- Task 1 建议 170-210 词，必须有改写题目、overview、2 个细节段；准确概述主要趋势/对比并引用关键数据
- Task 2 建议 280-330 词，必须有清晰立场、充分论证、具体例子、自然让步或反驳、明确结论
- 使用高级但自然准确的词汇和多样的语法结构，避免模板化、空泛、过短或低分表达
- 结构清晰，逻辑严密；拿去按 IELTS Writing 官方标准评分时应通常达到 Band 8.0-8.5
- 如果是 Task 1 图表描述，必须根据上面提供的 chart_data 或 table_data 中的实际数据来写作，准确引用数据值，描述趋势、对比和关键特征
- 如果是 Task 2，请直接根据题目展开论述

请输出完整的参考范文，不需要额外的解释。

{OUTPUT_RULES}"""

# ============================================================
# 关键词生成口语答案
# ============================================================
KEYWORD_ANSWER_PROMPT = """你是雅思口语教练。请根据学生提供的关键词，生成一个自然、流利、符合雅思 {part} 要求的完整英文答案。

题目/话题：
{question}

学生准备的关键词：
{keywords}

要求：
- 答案长度适合 {part}（Part 1 约30-60秒，Part 2 约1-2分钟，Part 3 约45-60秒）
- 自然融入学生提供的关键词
- 使用适当的连接词和过渡语
- 默认生成 Band 8.0-8.5 高分示范答案，展现词汇和语法的丰富性、准确性和自然度
- 不要为了迁就目标分数降低答案质量

请只输出有效 JSON，不要输出 Markdown，不要使用代码块：
{{
  "full_answer": "完整的英文答案，自然流畅，包含开头、主体和结尾",
  "answer_structure": "答案结构说明",
  "advanced_vocabulary": ["高级词汇1", "高级词汇2"],
  "useful_phrases": ["可套用短语1", "可套用短语2"],
  "improvement_tips": "针对这些关键词的改进建议"
}}"""

# ============================================================
# 词汇解释
# ============================================================
WORD_EXPLANATION_PROMPT = """你是雅思词汇教练。请解释雅思学习中这个英文词/短语的含义和用法。

词/短语：{word}

请按以下格式输出：
**翻译：** 中文释义
**常用搭配：** 搭配1、搭配2、搭配3
**雅思作文例句：** 例句

{output_rules}"""

# ============================================================
# 音频转写
# ============================================================
AUDIO_TRANSCRIPT_PROMPT = """请将以下音频内容转写为英文文本（这是一段雅思口语回答）。如果无法识别请回复 NO_TRANSCRIPT。不要回复其他内容。"""

# ============================================================
# 生成写作题目
# ============================================================
GENERATE_WRITING_TOPIC_TASK1_PROMPT = """你是雅思写作出题官。请生成一个雅思写作 Task 1 题目（小作文图表描述类）。

图表类型：{chart_type}
话题：{topic}

要求：
1. 图表类型为指定的类型：{chart_type}
2. 所有标签、数据、题目描述全部使用英文
3. 题目描述要清晰，写明图表展示了什么

{chart_specific_instructions}

请输出格式：

# 小作文题目

**图表类型：** {chart_type}

**题目：** 完整的英文题目描述，包含图表内容和写作要求

{chart_specific_fields}

**关键特征：**
- 特征1
- 特征2
- 特征3

**建议结构：** 建议的文章结构

{output_rules}"""

GENERATE_WRITING_TOPIC_TASK2_PROMPT = f"""你是雅思写作出题官。请生成一个雅思写作 Task 2 题目（大作文议论文类）。

话题：{{topic}}

要求：
1. 话题类别为指定的：{{topic}}
2. 题目描述要清晰，符合雅思 Task 2 真题风格
3. 所有内容使用英文

请输出格式：

# 大作文题目

**话题类别：** {{topic}}

**题目：** 完整的英文作文题目

**作文类型：** 同意不同意型/讨论双方观点型/利弊分析型/问题解决型

**关键论点：**
- 正方观点
- 反方观点

**建议结构：** 建议的文章结构

{OUTPUT_RULES}"""

GENERATE_WRITING_TOPIC_PROMPT_MAP = {
    "Task 1": GENERATE_WRITING_TOPIC_TASK1_PROMPT,
    "Task 2": GENERATE_WRITING_TOPIC_TASK2_PROMPT,
}

# ============================================================
# 提升建议（根据学习记录生成）
# ============================================================
IMPROVEMENT_SUGGESTIONS_PROMPT = """你是雅思备考教练。请根据学生的训练历史、弱项和当前水平，生成个性化重点提升建议。

学生情况：
- 当前综合水平：{current_level}
- 目标分数：{target_score}
- 弱项领域：{weak_areas_text}
- 需要提升：{gap} 分

最近训练记录：
{history_text}

请只输出有效 JSON，不要输出 Markdown，不要使用代码块：
{{
  "summary": "总体评价内容",
  "priority_areas": ["领域1", "领域2"],
  "suggestions": [
    {{
      "area": "领域名称",
      "current_issue": "当前问题描述",
      "action": "具体行动建议",
      "weekly_goal": "每周目标",
      "estimated_improvement": "预计提升幅度"
    }}
  ],
  "study_tips": ["技巧1", "技巧2"],
  "motivation": "鼓励语"
}}

要求：
- priority_areas 和 study_tips 必须是数组
- suggestions 中每个对象必须包含 area、current_issue、action、weekly_goal、estimated_improvement 字段
- 只输出 JSON"""

# ============================================================
# 作文思路互动（旧版 app_web.py mode="writing_ideas"）
# ============================================================
WRITING_IDEAS_OLD_PROMPT = f"""你是雅思写作教练。请围绕以下作文题目与学生的问题提供写作思路。

作文题目：
{{topic}}

学生想问：
{{question}}

请用中文回答，包含：
1. 题目理解
2. 可用立场
3. 2-3个论点
4. 可直接用于作文的英文表达
5. 一个简短提纲

{OUTPUT_RULES}"""

WORD_EXPLANATION_PROMPT_FULL = """请解释雅思学习中这个英文词/短语：{word}

请输出纯 JSON，不要包含 ```json 或其他标记，格式如下：
{{"translation":"中文释义","phrases":["搭配1","搭配2","搭配3"],"usage":"雅思作文例句"}}"""

# ============================================================
# 生成学习计划
# ============================================================
STUDY_PLAN_PROMPT = """你是雅思备考教练。请根据以下学生信息，生成一份个性化学习计划。

学生情况：
- 当前综合水平：{{current_level}}
- 目标分数：{{target_score}}
- 弱项领域：{{weak_areas_text}}
- 需要提升：{{gap}} 分
- 学习周期：{{weeks}} 周

最近训练记录：
{{history_text}}

请只输出有效 JSON，不要输出 Markdown，不要使用代码块：
{{
  "title": "学习计划",
  "overall_assessment": "总体评价内容",
  "priority_areas": ["优先提升领域1", "优先提升领域2"],
  "weekly_schedule": [
    {{
      "week": 1,
      "theme": "本周主题",
      "focus": "本周重点",
      "tasks": ["具体任务1", "具体任务2", "具体任务3"],
      "goal": "本周目标"
    }}
  ],
  "study_tips": ["学习建议1", "学习建议2"],
  "milestones": ["阶段性检查点1", "阶段性检查点2"]
}}

要求：
- weekly_schedule 必须按实际学习周期列出，从第 1 周到第 {{weeks}} 周
- priority_areas、tasks、study_tips、milestones 必须是数组
- 只输出 JSON"""
