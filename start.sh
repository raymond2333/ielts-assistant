#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

export FLASK_SECRET_KEY="${FLASK_SECRET_KEY:-ielts-shared-secret-key-2024}"
export WEB_PORT="${WEB_PORT:-8600}"
export STREAMLIT_PORT="${STREAMLIT_PORT:-8501}"
export SERVER_DOMAIN="${SERVER_DOMAIN:-127.0.0.1}"
export MYSQL_ENABLED="${MYSQL_ENABLED:-true}"
export MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
export MYSQL_PORT="${MYSQL_PORT:-3306}"
export MYSQL_USER="${MYSQL_USER:-ielts}"
export MYSQL_PASSWORD="${MYSQL_PASSWORD:-ielts}"
export MYSQL_DATABASE="${MYSQL_DATABASE:-ielts_learning}"
export LEGACY_STREAMLIT_URL="http://${SERVER_DOMAIN}:${STREAMLIT_PORT}"
export NEW_FLASK_URL="http://${SERVER_DOMAIN}:${WEB_PORT}"

echo ""
echo "╔════════════════════════════════════════╗"
echo "║        信达雅 IELTS 学习平台          ║"
echo "╠════════════════════════════════════════╣"
echo "║  Beta 版  → http://${SERVER_DOMAIN}:${WEB_PORT}   ║"
echo "║  稳定版  → http://${SERVER_DOMAIN}:${STREAMLIT_PORT}  ║"
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
