#!/bin/bash
# 전략 메시지 보내기 (서버에서 thermo 사용자로 실행). 인자: 번호 "3" 또는 "1,3", 비우면 전부
set -euo pipefail
APP=/opt/invest-thermometer
set -a
. "$APP/secrets.env"
set +a
cd "$APP/repo"
"$APP/venv/bin/python" send_message.py strategy_message.txt "${1:-}"
