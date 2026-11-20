# 전략 메시지를 텔레그램으로 보내기 (Oracle 서버에서 전송)
# 사용: & "$HOME\invest-thermometer\send_strategy.ps1"          → 3통 전부
#       & "$HOME\invest-thermometer\send_strategy.ps1" 3        → 3번째만 (1=QQQ, 2=SOXX, 3=VOO+공통)
param([string]$parts = "")
$key = Join-Path $HOME ".ssh\trading_ed25519"
$srv = "ubuntu@100.85.41.33"
ssh -i $key -o ConnectTimeout=15 $srv "sudo -u thermo /opt/invest-thermometer/repo/deploy/oracle/send_strategy.sh '$parts'"
