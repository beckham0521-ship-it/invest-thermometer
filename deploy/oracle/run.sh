#!/bin/bash
# Oracle 서버에서 매일 실행: 계산 → 텔레그램 → 결과를 GitHub에 올림(→ Pages 자동 배포)
# FORCE=1 이면 오늘 이미 보냈어도 다시 보냄 (수동 실행용)
set -uo pipefail
APP=/opt/invest-thermometer
cd "$APP/repo"
export GIT_SSH_COMMAND="ssh -i $APP/deploy_key -o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes"
export CI=1   # 실패 시 재시도 간격 60초

git pull --rebase -q || git rebase --abort 2>/dev/null

today=$(TZ=Asia/Seoul date +%F)
if [ "${FORCE:-0}" != "1" ] && [ "$(cat last_sent.txt 2>/dev/null)" = "$today" ]; then
  echo "오늘($today) 이미 보냄 → 건너뜀"
  exit 0
fi

set -a
. "$APP/secrets.env"
set +a
if [ -f "$APP/irp.json" ]; then export IRP_CONFIG="$(cat "$APP/irp.json")"; fi
rm -f .alert_sent

status=0
"$APP/venv/bin/python" thermometer.py || status=$?

# 파이썬이 시작도 못 하고 죽은 경우에도 알림
if [ "$status" != "0" ] && [ ! -f .alert_sent ]; then
  curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
    -d chat_id="${TELEGRAM_CHAT_ID}" \
    --data-urlencode text="⚠ 투자온도계 업데이트 실패 (Oracle 서버, 종료 코드 $status). 대시보드는 이전 값입니다." > /dev/null
fi

git add history_full*.csv history*.csv site last_sent.txt 2>/dev/null
if ! git diff --cached --quiet; then
  git -c user.name="thermometer-oracle" -c user.email="thermometer-oracle@users.noreply.github.com" \
    commit -q -m "update $today (oracle)"
  for i in 1 2 3; do
    git push -q && break
    git pull --rebase -q || { git rebase --abort; break; }
  done
fi
exit "$status"
