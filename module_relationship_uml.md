# 雅思学习助手模块关系图

```
@startuml 雅思学习助手模块关系图

skinparam backgroundColor white
skinparam componentStyle uml2
skinparam linetype ortho

' 定义主要模块
[app_web.py] as FlaskUI
[main.py] as StreamlitUI
[utils.py] as UtilsModule
[agents.py] as AgentsModule
[prompts.py] as PromptsModule

' 定义外部依赖
package "外部依赖" {
  [Streamlit] as Streamlit
  [Flask] as Flask
  [LangChain] as LangChain
  [通义千问API] as TongyiAPI
  [MySQL] as MySQL
  [Matplotlib] as Matplotlib
}

' 定义核心数据流
FlaskUI --> AgentsModule : 调用TongyiIELTSAssistant
FlaskUI --> UtilsModule : 调用工具函数
FlaskUI --> Flask : 路由 + 模板渲染
FlaskUI --> MySQL : 通过 database.py

StreamlitUI --> AgentsModule : 调用TongyiIELTSAssistant
StreamlitUI --> UtilsModule : 调用工具函数
StreamlitUI --> Streamlit : 构建界面
StreamlitUI --> MySQL : 通过 database.py

AgentsModule --> PromptsModule : 导入提示词模板
AgentsModule --> LangChain : 使用Agent框架
AgentsModule --> TongyiAPI : API调用

UtilsModule --> MySQL : 通过 database.py
UtilsModule --> Matplotlib : Task 1 图表生成

' app_web.py 主要组件
package "app_web.py (Flask)" {
  [writing() / speaking() / analysis()] as FlaskRoutes
  [record_result_filter] as RecFilter
  [simple_md_filter] as SndMd
  [build_task1_chart_assets] as ChartAssets
}

FlaskUI --> FlaskRoutes
FlaskUI --> RecFilter
FlaskUI --> SndMd
FlaskUI --> ChartAssets

' main.py 主要组件
package "main.py (Streamlit)" {
  [_render_speaking_part1] as Part1
  [_render_speaking_part2] as Part2
  [_render_speaking_part3] as Part3
  [_render_writing_task1] as Task1
  [_render_writing_task2] as Task2
  [_speak_button] as SpeakBtn
  [_display_record_result_data] as DisplayResult
}

StreamlitUI --> Part1
StreamlitUI --> Part2
StreamlitUI --> Part3
StreamlitUI --> Task1
StreamlitUI --> Task2
StreamlitUI --> SpeakBtn
StreamlitUI --> DisplayResult

' utils.py 核心函数
package "utils.py (跨版本共享)" {
  [parse_json_response] as Parser
  [parse_model_output] as ModelParser
  [parse_generated_topic_md] as TopicParser
  [build_task1_chart_assets] as ChartBuilder
  [simple_md_filter] as MdFilter
  [cross_login_token / verify_cross_token] as CrossLogin
  [save_user_progress / get_user_progress] as Progress
  [learning_record_title] as TitleFn
  [authenticate_user / register_user] as Auth
  [create_score_gauge / calculate_band_score] as Score
  [validate_essay_length] as WordCount
}

UtilsModule --> Parser
UtilsModule --> ModelParser
UtilsModule --> TopicParser
UtilsModule --> ChartBuilder
UtilsModule --> MdFilter
UtilsModule --> CrossLogin
UtilsModule --> Progress
UtilsModule --> TitleFn
UtilsModule --> Auth
UtilsModule --> Score
UtilsModule --> WordCount

' agents.py 主要类
package "agents.py (AI Agent)" {
  [TongyiIELTSAssistant] as Assistant
  [generate_writing_topic()] as GenTopic
  [generate_study_plan()] as GenPlan
  [generate_improvement_suggestions()] as GenSuggest
  [get_speaking_feedback_direct()] as SpeakFeedback
}

AgentsModule --> Assistant
Assistant --> GenTopic
Assistant --> GenPlan
Assistant --> GenSuggest
Assistant --> SpeakFeedback

' templates 依赖
package "Flask 模板" {
  [writing.html] as TmplWriting
  [speaking.html] as TmplSpeaking
  [dashboard.html] as TmplDashboard
  [analysis.html] as TmplAnalysis
}

FlaskUI --> TmplWriting
FlaskUI --> TmplSpeaking
FlaskUI --> TmplDashboard
FlaskUI --> TmplAnalysis

@enduml
```
