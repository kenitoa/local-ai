# Step 2 검증: 모든 서비스 /health 호출
$ErrorActionPreference = 'Continue'

$targets = @(
  @{ name = 'web-ui';            url = 'http://localhost:3000/health' },
  @{ name = 'backend';           url = 'http://localhost:8000/health' },
  @{ name = 'model-server';      url = 'http://localhost:8001/health' },
  @{ name = 'vision-server';     url = 'http://localhost:8002/health' },
  @{ name = 'embedding-server';  url = 'http://localhost:8003/health' },
  @{ name = 'language-worker';   url = 'http://localhost:8004/health' },
  @{ name = 'hardware-detector'; url = 'http://localhost:8005/health' }
)

foreach ($t in $targets) {
  try {
    $r = Invoke-RestMethod -Uri $t.url -TimeoutSec 3
    Write-Host ("[OK]   {0,-18} -> {1}" -f $t.name, ($r | ConvertTo-Json -Compress))
  } catch {
    Write-Host ("[FAIL] {0,-18} -> {1}" -f $t.name, $_.Exception.Message) -ForegroundColor Red
  }
}
