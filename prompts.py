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
- 只输出 JSON"""

# ============================================================
# 口语反馈
# ============================================================
SPEAKING_FEEDBACK_PROMPT = """你是专业的雅思口语考官，请对以下口语回答进行专业评分和反馈。

考试部分：{part}
题目：{question}
考生回答：{user_response}
目标分数：{target_score}

请只输出有效 JSON，不要输出 Markdown，不要使用代码块：
{{
  "overall_score": 6.5,
  "breakdown": {{
    "fluency_coherence": {{"score": 6.5, "strengths": ["优点"], "weaknesses": ["待改进点"], "suggestions": ["建议"]}},
    "lexical_resource": {{"score": 6.5, "vocabulary_analysis": "词汇分析", "suggested_words": ["推荐词汇"]}},
    "grammatical_range_accuracy": {{"score": 6.5, "grammar_analysis": "语法分析", "common_errors": ["常见错误"]}},
    "pronunciation": {{"score": 6.5, "pronunciation_analysis": "发音分析", "improvement_tips": ["改进建议"]}}
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

请只输出有效 JSON，不要输出 Markdown，不要使用代码块：
{{
  "overall_score": 6.5,
  "breakdown": {{
    "fluency_coherence": {{"score": 6.5, "strengths": ["优点"], "weaknesses": ["待改进点"], "suggestions": ["建议"]}},
    "lexical_resource": {{"score": 6.5, "vocabulary_analysis": "词汇分析", "suggested_words": ["推荐词汇"]}},
    "grammatical_range_accuracy": {{"score": 6.5, "grammar_analysis": "语法分析", "common_errors": ["常见错误"]}},
    "pronunciation": {{"score": 6.5, "pronunciation_analysis": "发音分析", "improvement_tips": ["改进建议"]}}
  }},
  "improved_response": "优化后的回答示例",
  "practice_recommendations": ["练习建议1", "练习建议2"]
}}"""

# ============================================================
# 小作文批改（Task 1）
# ============================================================
WRITING_TASK1_CORRECTION_PROMPT = f"""你是专业的雅思写作 Task 1 考官，请对以下小作文进行详细批改。

图表类型：{{task_type}}
考生作文：{{essay_content}}
目标分数：{{target_score}}

请按以下格式输出：

# 写作批改结果

## 总分：X 分

### 分数段描述
描述内容

## 任务完成度（评分：X）
评价和改进建议

## 连贯与衔接（评分：X）
评价和改进建议

## 词汇资源（评分：X）
评价和改进建议

## 语法多样性与准确性（评分：X）
评价和改进建议

## 优点
- 优点1
- 优点2

## 改进建议
- 改进点1
- 改进点2

## 修改建议
语法和词汇修正

{OUTPUT_RULES}"""

# ============================================================
# 大作文批改（Task 2）
# ============================================================
WRITING_TASK2_CORRECTION_PROMPT = f"""你是专业的雅思写作 Task 2 考官，请对以下大作文进行详细批改。

话题：{{topic}}
作文类型：{{essay_type}}
考生作文：{{essay_content}}
目标分数：{{target_score}}

请按以下格式输出：

# 写作批改结果

## 总分：X 分

### 分数段描述
描述内容

## 任务回应（评分：X）
评价和改进建议

## 连贯与衔接（评分：X）
评价和改进建议

## 词汇资源（评分：X）
评价和改进建议

## 语法多样性与准确性（评分：X）
评价和改进建议

## 优点
- 优点1
- 优点2

## 改进建议
- 改进点1
- 改进点2

## 修改建议
语法和词汇修正

{OUTPUT_RULES}"""

# ============================================================
# 口语串题
# ============================================================
THEME_LINKING_PROMPT = """你是雅思口语串题专家，请将以下话题进行有机串联。

需要串联的话题：{topics}
核心主题：{main_theme}
目标分数：{target_score}

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
- 使用高级词汇和多样的语法结构
- 结构清晰，逻辑严密
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
- 展现词汇和语法的丰富性

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
