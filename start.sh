#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# 解析命令行参数
while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--mysql-port)
      export MYSQL_PORT="$2"
      shift 2
      ;;
    -u|--mysql-user)
      export MYSQL_USER="$2"
      shift 2
      ;;
    -pw|--mysql-password)
      export MYSQL_PASSWORD="$2"
      shift 2
      ;;
    *)
      echo "用法: bash start.sh [选项]"
      echo "选项:"
      echo "  -p, --mysql-port <端口号>      MySQL 端口 (默认: 3306)"
      echo "  -u, --mysql-user <用户名>      MySQL 用户名 (默认: ielts)"
      echo "  -pw, --mysql-password <密码>   MySQL 密码 (默认: ielts)"
      echo "示例:"
      echo "  bash start.sh -p 13306 -u root -pw mypassword"
      exit 1
      ;;
  esac
done


export FLASK_SECRET_KEY="${FLASK_SECRET_KEY:-ielts-shared-secret-key-2024}"
export WEB_PORT="${WEB_PORT:-8600}"
export STREAMLIT_PORT="${STREAMLIT_PORT:-8501}"
export MYSQL_ENABLED="${MYSQL_ENABLED:-true}"
export MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
export MYSQL_PORT="${MYSQL_PORT:-3306}"
export MYSQL_USER="${MYSQL_USER:-ielts}"
export MYSQL_PASSWORD="${MYSQL_PASSWORD:-ielts}"
export MYSQL_DATABASE="${MYSQL_DATABASE:-ielts_learning}"
if [ -n "${SERVER_DOMAIN:-}" ]; then
  export LEGACY_STREAMLIT_URL="${LEGACY_STREAMLIT_URL:-http://${SERVER_DOMAIN}:${STREAMLIT_PORT}}"
  export NEW_FLASK_URL="${NEW_FLASK_URL:-http://${SERVER_DOMAIN}:${WEB_PORT}}"
fi
DISPLAY_FLASK_URL="${NEW_FLASK_URL:-当前访问域名:${WEB_PORT}}"
DISPLAY_STREAMLIT_URL="${LEGACY_STREAMLIT_URL:-当前访问域名:${STREAMLIT_PORT}}"

echo ""
echo "╔════════════════════════════════════════╗"
echo "║        信达雅 IELTS 学习平台          ║"
echo "╠════════════════════════════════════════╣"
echo "║  Beta 版  → ${DISPLAY_FLASK_URL}"
echo "║  稳定版  → ${DISPLAY_STREAMLIT_URL}"
echo "║  跨版本免登录已启用                    ║"
echo "╚════════════════════════════════════════╝"
echo ""

# 杀掉已占用的端口
echo ">>> 清理旧进程..."
for port in "${WEB_PORT}" "${STREAMLIT_PORT}"; do
  PIDS=$(lsof -ti:${port} 2>/dev/null || true)
  if [ -n "${PIDS}" ]; then
    echo "  - 发现占用端口 ${port} 的进程: ${PIDS}，正在终止..."
    echo "${PIDS}" | xargs kill -9 2>/dev/null || true
  fi
done
sleep 1

trap 'echo ""; echo "正在关闭所有服务..."; kill 0 2>/dev/null; exit 0' INT TERM

echo ">>> 启动 Beta 版 (端口 ${WEB_PORT})..."
python3 app_web.py &
FLASK_PID=$!

echo ">>> 启动稳定版 (端口 ${STREAMLIT_PORT})..."
streamlit run main.py --server.port "${STREAMLIT_PORT}" --server.headless true 2>&1 &
ST_PID=$!

echo ""
echo "两个服务已启动，按 Ctrl+C 同时关闭。"
echo ""

wait $FLASK_PID $ST_PID
