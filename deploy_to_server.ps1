# PC에서 고친 코드를 Oracle 서버에 올리기 (기록 CSV·대시보드 결과는 서버 것이 정본이라 건드리지 않음)
# 사용: & "$HOME\invest-thermometer\deploy_to_server.ps1"
$ErrorActionPreference = "Stop"
$key = Join-Path $HOME ".ssh\trading_ed25519"
$srv = "ubuntu@100.85.41.33"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$files = @("thermometer.py", "template.html", "strategy_message.txt", "send_message.py", "requirements.txt",
           "deploy/oracle/run.sh", "deploy/oracle/install.sh", "deploy/oracle/send_strategy.sh",
           "deploy/oracle/invest-thermometer.service", "deploy/oracle/invest-thermometer.timer")
$tgz = Join-Path $env:TEMP "thermo-code.tgz"
tar -czf $tgz -C $dir @files
scp -i $key -q $tgz "${srv}:/tmp/thermo-code.tgz"
$remote = @'
set -e
APP=/opt/invest-thermometer
sudo -u thermo tar -xzf /tmp/thermo-code.tgz -C $APP/repo
rm -f /tmp/thermo-code.tgz
sudo -u thermo sed -i 's/\r$//' $APP/repo/deploy/oracle/*.sh
sudo chmod 755 $APP/repo/deploy/oracle/*.sh
sudo install -m 644 $APP/repo/deploy/oracle/invest-thermometer.service $APP/repo/deploy/oracle/invest-thermometer.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart invest-thermometer.timer
sudo -u thermo $APP/venv/bin/pip install -q --no-cache-dir -r $APP/repo/requirements.txt
cd $APP/repo
sudo -u thermo git add -A
sudo -u thermo git -c user.name=thermometer-deploy -c user.email=deploy@local commit -q -m "deploy from PC $(TZ=Asia/Seoul date '+%F %H:%M')" || true
echo "서버 반영 완료: $(sudo -u thermo git log --oneline -1)"
'@
$remote -replace "`r", "" | ssh -i $key $srv "bash -s"
