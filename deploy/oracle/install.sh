#!/bin/bash
# Oracle 서버 설치 (sudo bash install.sh). 여러 번 실행해도 안전.
set -euo pipefail
APP=/opt/invest-thermometer
REPO=git@github.com:beckham0521-ship-it/invest-thermometer.git

id thermo >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin thermo
mkdir -p "$APP"
chown thermo:thermo "$APP"
chmod 750 "$APP"

# GitHub 쓰기용 배포 키 (이 저장소 전용)
if [ ! -f "$APP/deploy_key" ]; then
  sudo -u thermo ssh-keygen -t ed25519 -N "" -C "invest-thermometer@oracle" -f "$APP/deploy_key" >/dev/null
fi
echo "=== 배포 키 공개키 ==="
cat "$APP/deploy_key.pub"

# 비밀값 파일 (토큰은 별도 스크립트로 채움)
if [ ! -f "$APP/secrets.env" ]; then
  printf 'TELEGRAM_TOKEN=\nTELEGRAM_CHAT_ID=\n' > "$APP/secrets.env"
fi
chown thermo:thermo "$APP/secrets.env"
chmod 600 "$APP/secrets.env"

# 파이썬 환경
if ! python3 -m venv --help >/dev/null 2>&1 || ! dpkg -s python3-venv >/dev/null 2>&1; then
  apt-get install -y -q python3-venv >/dev/null
fi
[ -d "$APP/venv" ] || sudo -u thermo python3 -m venv "$APP/venv"
echo "venv OK"
