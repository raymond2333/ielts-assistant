# MySQL 配置说明

项目默认仍可使用内存存储运行。要把登录账号、用户 AI 供应商配置、API Key、用户档案和学习记录保存到 MySQL，请设置环境变量：

```bash
export MYSQL_ENABLED=true
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
export MYSQL_USER=root
export MYSQL_PASSWORD=your_mysql_password
export MYSQL_DATABASE=ielts_learning
```

启动应用（同时启动 Flask Beta 版和 Streamlit 稳定版）：

```bash
bash start.sh
```

或者单独启动 Streamlit 版：

```bash
streamlit run main.py
```

首次连接时应用会自动创建数据库和以下表：

- `users`：保存每个用户的登录密码哈希、AI供应商配置、API Key、听力/口语/阅读/写作四项当前水平、综合当前水平、目标分数、弱项、每周学习时间和考试日期
- `study_progress`：保存口语反馈、作文批改、学习计划等学习记录

侧边栏会显示数据库状态。如果 MySQL 未启用或连接失败，应用会回退到内存记录，避免影响练习流程；但用户 AI 配置和 API Key 无法跨重启持久保存。
