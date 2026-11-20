# Oracle 서버에 텔레그램 봇 토큰 저장 (입력값은 화면에 안 보임, 이 PC·대화에도 남지 않음)
# 사용: PowerShell 에서  & "$HOME\invest-thermometer\set_server_token.ps1"
$ErrorActionPreference = "Stop"
$key  = Join-Path $HOME ".ssh\trading_ed25519"
$sec  = Read-Host "텔레그램 봇 토큰 붙여넣기 (화면에 안 보여요)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
try {
    $tok = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    $OutputEncoding = New-Object Text.UTF8Encoding $false
    $tok | ssh -i $key -o ConnectTimeout=15 ubuntu@100.85.41.33 "sudo /usr/local/sbin/thermo-set-token"
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    $tok = $null
}
if ($LASTEXITCODE -ne 0) { Write-Host "저장 실패" -ForegroundColor Red; exit 1 }
$t = Read-Host "지금 서버에서 테스트 메시지를 보낼까요? (y/n)"
if ($t -eq "y") {
    ssh -i $key -o ConnectTimeout=15 ubuntu@100.85.41.33 "sudo systemd-run --quiet --uid=thermo --gid=thermo --setenv=FORCE=1 /opt/invest-thermometer/repo/deploy/oracle/run.sh"
    Write-Host "요청함. 1~2분 뒤 텔레그램 확인." -ForegroundColor Green
}
