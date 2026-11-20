# 내 IRP 보유 수량·남은 투자금 업데이트 → GitHub 비밀값 IRP_CONFIG (공개 페이지에는 안 나옴)
# 사용: PowerShell 에서  & "$HOME\invest-thermometer\update_irp.ps1"
$ErrorActionPreference = "Stop"
$gh   = "C:\Program Files\GitHub CLI\gh.exe"
$repo = "beckham0521-ship-it/invest-thermometer"
$dir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$file = Join-Path $dir "irp_local.json"
$c = Get-Content $file -Raw -Encoding UTF8 | ConvertFrom-Json

function Ask($label, $cur) {
    $v = Read-Host "$label [지금 $cur, 그대로면 엔터]"
    if ([string]::IsNullOrWhiteSpace($v)) { return [int64]$cur }
    return [int64]($v -replace '[, 원주]', '')
}

Write-Host "`n=== 내 IRP 업데이트 ===" -ForegroundColor Cyan
$c.holdings.ndx = Ask "TIGER 미국나스닥100 보유 수량(주)" $c.holdings.ndx
$c.holdings.sox = Ask "TIGER 미국필라델피아반도체나스닥 보유 수량(주)" $c.holdings.sox
$c.holdings.spx = Ask "KODEX 미국S&P500 보유 수량(주)" $c.holdings.spx
$c.remaining    = Ask "남은 투자금(원, 3000만 원까지 남은 금액)" $c.remaining

$json = $c | ConvertTo-Json -Compress -Depth 5
[IO.File]::WriteAllText($file, $json, (New-Object Text.UTF8Encoding $false))
$OutputEncoding = New-Object Text.UTF8Encoding $false   # BOM 없이 보내기
$json | & $gh secret set IRP_CONFIG --repo $repo
# Oracle 서버(매일 계산하는 곳)에도 복사
$key = Join-Path $HOME ".ssh\trading_ed25519"
$json | ssh -i $key -o ConnectTimeout=15 ubuntu@100.85.41.33 "sudo tee /opt/invest-thermometer/irp.json >/dev/null && sudo chown thermo:thermo /opt/invest-thermometer/irp.json && sudo chmod 600 /opt/invest-thermometer/irp.json"
if ($LASTEXITCODE -ne 0) { Write-Host "⚠ 서버 복사 실패 (Tailscale 연결 확인). GitHub에는 저장됨." -ForegroundColor Yellow }
Write-Host "저장 완료: 나스닥100 $($c.holdings.ndx)주 / 반도체 $($c.holdings.sox)주 / S&P500 $($c.holdings.spx)주 / 남은 투자금 $($c.remaining)원" -ForegroundColor Green

$again = Read-Host "지금 텔레그램 메시지를 다시 받을까요? (y/n)"
if ($again -eq "y") {
    ssh -i $key -o ConnectTimeout=15 ubuntu@100.85.41.33 "sudo systemd-run --quiet --uid=thermo --gid=thermo --setenv=FORCE=1 /opt/invest-thermometer/repo/deploy/oracle/run.sh"
    Write-Host "서버에 요청함. 1~2분 뒤 텔레그램 확인."
}
