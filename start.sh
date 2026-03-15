#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

LOG_FILE="/tmp/summ-kakaobot.log"

# 기존 프로세스 종료
PID=$(lsof -ti:8001 2>/dev/null || true)
if [ -n "$PID" ]; then
  echo "기존 summ_kakaobot(PID=$PID) 종료 중..."
  kill "$PID"
  sleep 1
fi

echo "summ_kakaobot 시작 중 (port 8001)..."
source .venv/bin/activate
nohup uvicorn app.main:app --host 0.0.0.0 --port 8001 > "$LOG_FILE" 2>&1 &
echo "PID: $!"

# 헬스체크
for i in {1..10}; do
  sleep 1
  if curl -sf http://localhost:8001/health > /dev/null 2>&1; then
    echo "summ_kakaobot 정상 기동 완료"
    exit 0
  fi
done

echo "summ_kakaobot 기동 실패. 로그: $LOG_FILE"
exit 1
