# 信达雅使用文档

## 项目简介

信达雅是一个基于 Flask/Streamlit、LangChain 和多模型 API 的 IELTS 备考应用，面向雅思口语、写作和词汇学习场景。系统支持用户中心、口语 Part 1、Part 2、Part 3 题目生成与反馈，写作 Task 1、Task 2 批改，作文思路互动，雅思词汇背诵，个性化学习计划（AI 生成），以及基于用户 ID 的学习档案和学习记录管理。

项目已支持 MySQL 持久化存储。启用 MySQL 后，每个用户可以使用自己的账号登录，并保存个人 AI 供应商配置、API Key、学习档案、口语反馈、写作批改分数和学习计划记录；未启用 MySQL 时，系统会自动回退到 Streamlit 内存状态，方便本地快速体验。

## 主要功能

### Flask 新版（推荐）
- **学习总览**：展示综合水平、目标分数、四项水平、最近学习记录。
- **用户设置**：独立的设置页面，管理个人信息、学习目标、四项水平和各模型 API Key。
- **口语练习**：Part 1/2/3 题目生成，支持 AI 反馈批改（评分 + 分项评价 + 改进建议）、中文思路转英文答案。
- **口语串题**：多话题统一主题串联，中英文双语输出。
- **作文批改**：Task 1/2 批改，随机生成作文题目（含图表图片），思路互动，一键填充到练习区。
- **学习分析**：记录总览 + AI 个性化学习计划（基于训练历史）。
- **背单词**：雅思核心词库 + AI 查词 + 收藏。
- **跨版本免登录**：Flask ↔ Streamlit 通过 HMAC 签名 token 互跳，无需重复登录。

### Streamlit 旧版
- 口语 Part 1/2/3 题目生成与 AI 反馈批改。
- Part 2 关键词 → 完整答案生成。
- 作文批改（Task 1/2）。
- 口语串题（中英文双语输出）。
- 学习分析与 AI 个性化学习计划。
- MySQL 持久化（用户、API Key、档案、学习记录）。

## 项目结构

```text
ielts/
├── main.py                    # Streamlit 主界面和页面交互逻辑
├── app_web.py                 # Flask 新版（学习总览 + 用户设置分离）
├── utils.py                   # 跨版本共享工具函数
├── agents.py                  # 多模型 Agent，口语/写作/串题/反馈/关键词/学习计划生成
├── prompts.py                 # 口语、写作、串题、学习计划等提示词模板
├── database.py                # MySQL 连接、建库建表、用户档案和学习记录
├── start.sh                   # 一键启动脚本（同时启动 Flask + Streamlit）
├── requirements.txt           # Python 依赖列表
├── .env.example               # 环境变量配置示例
├── MYSQL_SETUP.md             # MySQL 配置说明
├── static/
│   ├── styles.css             # 全局样式
│   ├── app.js                 # 侧边栏折叠 + 朗读语音 + 删除录音
│   └── word_tools.js          # 单词收藏工具
├── data/
│   └── charts/                # Task 1 图表图片缓存
└── templates/
    ├── auth.html              # 登录/注册页
    ├── dashboard.html          # 学习总览
    ├── settings.html           # 用户设置（个人信息 + API 配置）
    ├── speaking.html           # 口语练习（含计时器 + 反馈 + 关键词生成）
    ├── writing.html            # 作文批改（含随机生成题目）
    ├── theme_linking.html      # 口语串题
    ├── analysis.html           # 学习分析
    ├── vocabulary.html         # 背单词
    └── assistant.html          # 学习助手
```

## 环境要求

- Python 3.10 或以上版本
- 可用的 AI API Key，支持通义千问 Dashscope、DeepSeek、OpenAI 和 OpenAI 兼容接口
- 可选：MySQL 8.0 或兼容版本

Python 依赖见 `requirements.txt`：

```text
streamlit
flask
pandas
langchain
langchain-community
dashscope
mysql-connector-python
langchain-openai
openai
requests
markupsafe
```

## 安装依赖

建议先创建虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

安装依赖：

```bash
pip install -r requirements.txt
```

## 环境变量配置

### 基础配置

应用需要 AI API Key 才能调用模型。推荐登录后在侧边栏选择供应商并保存当前用户自己的 API Key；环境变量只作为兜底默认值：

```bash
export DASHSCOPE_API_KEY=your_dashscope_api_key
export DEEPSEEK_API_KEY=your_deepseek_api_key
export OPENAI_API_KEY=your_openai_api_key
```

也可以参考 `.env.example` 创建自己的环境变量配置。

### MySQL 配置

如果希望保存登录账号、每个用户的 API Key、学习档案和学习记录，请启用 MySQL：

```bash
export MYSQL_ENABLED=true
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
export MYSQL_USER=root
export MYSQL_PASSWORD=your_mysql_password
export MYSQL_DATABASE=ielts_learning
```

可选默认用户 ID：

```bash
export IELTS_DEFAULT_USER_ID=default_user
```

首次连接 MySQL 时，应用会自动创建数据库和数据表，无需手动执行 SQL。

## 启动项目

### 一键启动（推荐）

使用 `start.sh` 脚本同时运行两个版本，自动配置跨版本免登录：

```bash
bash start.sh
```

启动后访问：
- Beta 版：`http://localhost:8600`
- 稳定版：`http://localhost:8501`

> Ctrl+C 可同时关闭两个服务。Beta 版使用 waitress 生产级 WSGI 服务器运行，无开发服务器警告。

**自定义 MySQL 端口**：如果 MySQL 不在默认的 3306 端口，用 `-p` 参数指定端口即可：

```bash
bash start.sh -p 13306
```

> **注意**：如果使用 `nohup` 后台运行，同样支持参数：
> ```bash
> nohup bash start.sh -p 13306 > output.log 2>&1 &
> ```

其他环境变量（如数据库地址、密码等）也可通过前缀覆盖，例如：

```bash
MYSQL_HOST=192.168.1.100 MYSQL_PASSWORD=myPass bash start.sh -p 13306
```

### 单独启动 Beta 版

这是推荐使用的版本，学习总览与用户设置已拆分为独立页面：

```bash
MYSQL_ENABLED=true \
MYSQL_HOST=127.0.0.1 \
MYSQL_PORT=3306 \
MYSQL_USER=ielts \
MYSQL_PASSWORD=ielts \
MYSQL_DATABASE=ielts_learning \
WEB_PORT=8600 \
FLASK_SECRET_KEY=your-secret-key \
python3 app_web.py
```

如果 MySQL 在其他端口（如 13306），修改 `MYSQL_PORT` 即可：

```bash
MYSQL_PORT=13306 python3 app_web.py
```

访问：

```text
http://localhost:8600
```

页面导航：
- **学习总览**（`/dashboard`）：综合水平、四项分数、快速入口、最近学习记录
- **用户设置**（`/settings`）：个人信息、学习目标、各模型 API Key 配置
- **口语练习**（`/speaking`）：Part 1/2/3，含计时器、AI 反馈、关键词生成答案
- **作文批改**（`/writing`）：随机生成题目（含图表图片）、思路互动、Task 1/2 批改
- **口语串题**（`/theme-linking`）：多话题统一主题
- **学习分析**（`/analysis`）：学习记录总览 + AI 个性化学习计划
- **背单词**（`/vocabulary`）：雅思词库 + AI 查词

> `FLASK_SECRET_KEY` 同时用于跨版本免登录的 HMAC token 签名，两个版本需设置相同的值。

### Streamlit 练习版本

在项目根目录运行：

```bash
streamlit run main.py
```

启动后浏览器访问：

```text
http://localhost:8501
```

如果端口被占用，可以指定其他端口：

```bash
streamlit run main.py --server.port 8502
```

## 使用流程

### 1. 登录用户

打开页面后，先输入用户 ID 和登录密码。首次登录时，如果 MySQL 中不存在该用户，系统会自动创建用户；后续使用同一用户 ID 和密码登录即可。

未启用 MySQL 时也可以临时登录体验，但用户 API Key 无法跨应用重启持久保存。

注册成功后系统会自动登录，不需要再次输入账号密码。

### 2. 保存当前用户 AI 配置

登录成功后，在左侧侧边栏的"API配置"区域选择 AI 供应商，填写模型名称和 API Key，点击"保存当前用户AI配置"。保存后系统会自动初始化 Agent。

当前支持：

- 通义千问 Dashscope，默认模型 `qwen-turbo`
- DeepSeek，默认模型 `deepseek-chat`
- OpenAI，默认模型 `gpt-4o-mini`
- OpenAI兼容接口，可自定义模型名称和 Base URL

启用 MySQL 后，该 AI 配置会绑定到当前用户；下次登录同一用户时会自动加载，无需重复输入。

### 3. 设置用户档案

在侧边栏的"用户档案"区域填写：

- 当前雅思水平：听力、口语、阅读、写作四个分项
- 目标分数
- 每周学习时间
- 弱项领域
- 考试日期

点击"更新档案"后，若 MySQL 已启用，档案会保存到数据库；否则保存在当前会话中。

### 4. 口语练习

进入"口语练习"标签页，选择：

- Part 1：日常话题问答
- Part 2：个人陈述题目卡（含 1 分钟准备 + 2 分钟发言计时器）
- Part 3：深入讨论题

生成题目后输入自己的回答，点击反馈按钮即可获得评分和改进建议。系统会自动保存包含分数的练习记录。

支持**关键词生成答案**：在 Part 2 输入关键词，AI 围绕关键词生成完整流利答案。

### 5. 口语串题

进入"口语串题"标签页，选择至少两个话题，并输入一个核心主题，例如"个人成长""环境保护""文化交流"。系统会生成：

- 统一核心主题
- 各话题的中英文适配回答
- 关键元素
- 过渡短语
- 通用词汇库
- 练习策略

### 6. 作文批改

进入"作文批改"标签页，选择 Task 1 或 Task 2：

**Task 1（小作文 - 图表描述）**：
- 点击「🎲 生成小作文题目」一键生成含随机图表类型（线形图/柱状图/饼图）的题目
- 图表图片直接显示，无需手动展开
- 题目自动填充到思路互动区和练习区

**Task 2（大作文 - 议论文）**：
- 点击「🎲 生成大作文题目」一键生成含话题类别和关键论点的题目
- 题目自动填充到思路互动区和练习区

批改结果包括：

- 总体分数
- 分项评分（任务完成度、连贯衔接、词汇资源、语法范围）
- 优点
- 改进建议
- 语法和词汇修正
- 修正后的作文或范文示例

批改完成后，系统会自动保存学习记录。

### 7. 学习分析

进入"学习分析"标签页，可以查看：

- 每周学习时长
- 距离考试天数
- 需要提升的分数
- 练习历史（可筛选日期）
- 分数趋势图
- 针对弱项的学习建议（AI 生成）

点击"📅 生成详细学习计划"后，系统会结合用户目标、弱项和训练历史记录，由 AI 生成个性化学习计划（按周排列详细安排），生成后自动保存到学习记录。再次进入页面时计划自动加载，可通过「🔄 重新生成」按钮更新。

## MySQL 数据表说明

启用 MySQL 后，系统会自动创建两个表。

### users

保存用户档案：

- `user_id`：用户唯一标识
- `password_hash`：登录密码哈希
- `dashscope_api_key`：兼容旧版本的通义千问 API Key 字段
- `ai_provider`：当前用户选择的 AI 供应商
- `ai_model`：当前用户选择的模型名称
- `ai_base_url`：OpenAI兼容接口地址
- `ai_api_keys`：当前用户保存的各供应商 API Key，JSON 格式
- `current_level`：四项平均后的综合当前水平，按雅思规则舍入为 `.0` 或 `.5`
- `listening_level`：听力当前水平
- `speaking_level`：口语当前水平
- `reading_level`：阅读当前水平
- `writing_level`：写作当前水平
- `target_score`：目标分数
- `weak_areas`：弱项领域，JSON 格式
- `study_time`：每周学习时间
- `exam_date`：考试日期
- `created_at`：创建时间
- `updated_at`：更新时间

### study_progress

保存学习记录：

- `id`：记录 ID
- `user_id`：关联用户 ID
- `activity`：学习活动类型
- `score`：本次练习分数，可为空
- `data`：完整学习数据，JSON 格式
- `created_at`：记录创建时间

## 常见问题

### 页面提示未启用 MySQL，是否影响使用？

不影响基础体验。未启用 MySQL 时，系统使用内存存储，适合临时体验。但刷新、重启或关闭应用后，用户 API Key、学习档案和学习记录可能丢失。

### MySQL 连接失败怎么办？

检查以下配置：

- `MYSQL_ENABLED` 是否为 `true`
- MySQL 服务是否已启动
- `MYSQL_HOST`、`MYSQL_PORT` 是否正确
- 用户名和密码是否正确
- 当前用户是否有创建数据库和表的权限

### 为什么登录后仍提示需要保存 API Key？

说明当前用户还没有保存 AI API Key，或 MySQL 未启用导致上次保存的 API Key 没有持久化。请在侧边栏"API配置"中选择供应商并保存当前用户 AI 配置。

### 为什么生成题目或批改时报错？

常见原因：

- AI API Key 未填写或无效
- 网络无法访问对应模型服务
- 模型返回内容不是标准格式，页面会尽量显示原始响应或错误信息

### 朗读功能听起来生硬怎么办？

朗读使用浏览器原生 SpeechSynthesis API 进行整句合成。可在浏览器设置中选择更自然的语音包（如 Microsoft Jenny、Google US English 等）。

### 学习计划可以重新生成吗？

可以。已生成的学习计划会持久化保存，页面顶部显示「🔄 重新生成」按钮，点击后可基于最新训练记录重新由 AI 生成。

## 开发说明

核心调用链如下：

```text
# Flask 新版
app_web.py
  ├── 调用 agents.py 中的 TongyiIELTSAssistant
  ├── 通过 utils.py 间接调用 database.py 读写 MySQL
  └── 模板渲染 templates/*.html + static/*

# Streamlit 旧版
main.py
  ├── 调用 agents.py 中的 TongyiIELTSAssistant
  ├── 通过 utils.py 间接调用 database.py 读写 MySQL
  └── Streamlit 内置渲染

utils.py（跨版本共享）
  ├── parse_json_response() / parse_model_output() — JSON/Markdown 解析
  ├── parse_generated_topic_md() — 从 AI Markdown 提取结构化作文题目
  ├── build_task1_chart_assets() — 生成 Task 1 图表图片
  ├── simple_md_filter() — Markdown → HTML（不依赖 Flask/Streamlit）
  ├── cross_login_token() / verify_cross_token() — 跨版本免登录
  ├── learning_record_title() — 根据 activity 返回语义化标题
  ├── save_user_progress() / get_user_progress() — 进度管理
  └── authenticate_user() / register_user() / load_user_profile() — 用户包装

agents.py
  ├── 使用 prompts.py 中的提示词模板
  ├── generate_writing_topic() — 生成作文题目（输出 Markdown 格式）
  ├── generate_study_plan() — AI 生成个性化学习计划
  ├── generate_answer_from_keywords() — 关键词 → 完整答案
  ├── get_speaking_feedback_direct() — 直接调用 LLM 反馈
  └── 通过 LangChain 调用通义千问、DeepSeek、OpenAI 或 OpenAI 兼容模型

database.py
  ├── 自动初始化 MySQL 数据库和表
  ├── 保存/读取用户档案
  └── 保存/读取学习进度
```

跨版本免登录原理：
1. 两个版本共享 `FLASK_SECRET_KEY` 环境变量
2. 跳转 URL 附带 `?user_id=xxx&x_token=HMAC签名`
3. 目标版本验证 token → 通过 `load_user_profile()` 确认用户存在 → 自动登录

如果要扩展新的练习类型，推荐流程：

1. 在 `prompts.py` 增加提示词模板。
2. 在 `agents.py` 增加对应模型调用方法。
3. 在主文件中增加页面入口和结果展示。
4. 调用 `save_user_progress()` 保存用户学习记录。

## 验证命令

修改代码后可以先运行语法检查：

```bash
python3 -m py_compile main.py utils.py database.py agents.py prompts.py app_web.py
```

再启动应用验证：

```bash
bash start.sh
```
