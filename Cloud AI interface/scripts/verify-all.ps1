param(
  [int]$ApiPort = 5088
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Results = New-Object System.Collections.Generic.List[object]
$Failures = 0

function Add-Result {
  param(
    [string]$Stage,
    [string]$Name,
    [string]$Status,
    [string]$Detail
  )

  $script:Results.Add([ordered]@{
    stage = $Stage
    name = $Name
    status = $Status
    detail = $Detail
  }) | Out-Null

  if ($Status -eq "FAIL") {
    $script:Failures += 1
  }

  Write-Host "[$Status] $Stage - $Name :: $Detail"
}

function Invoke-Required {
  param(
    [string]$Stage,
    [string]$Name,
    [scriptblock]$Action
  )

  try {
    $detail = & $Action
    Add-Result -Stage $Stage -Name $Name -Status "PASS" -Detail ([string]$detail)
  }
  catch {
    Add-Result -Stage $Stage -Name $Name -Status "FAIL" -Detail $_.Exception.Message
  }
}

function Invoke-Optional {
  param(
    [string]$Stage,
    [string]$Name,
    [scriptblock]$Action
  )

  try {
    $detail = & $Action
    Add-Result -Stage $Stage -Name $Name -Status "PASS" -Detail ([string]$detail)
  }
  catch {
    Add-Result -Stage $Stage -Name $Name -Status "WARN" -Detail $_.Exception.Message
  }
}

function Invoke-CommandText {
  param([string]$Command)

  $output = Invoke-Expression $Command 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw ($output | Out-String)
  }

  return (($output | Select-Object -Last 3) -join " ").Trim()
}

function Invoke-JsonPost {
  param(
    [string]$Path,
    [hashtable]$Body
  )

  $json = $Body | ConvertTo-Json -Depth 8
  return Invoke-RestMethod -Uri "http://localhost:$ApiPort$Path" -Method Post -ContentType "application/json" -Body $json
}

function Wait-Api {
  for ($i = 0; $i -lt 20; $i += 1) {
    try {
      return Invoke-RestMethod -Uri "http://localhost:$ApiPort/api/health"
    }
    catch {
      Start-Sleep -Milliseconds 500
    }
  }

  throw "ASP.NET API did not become reachable on port $ApiPort."
}

Push-Location $RepoRoot

try {
  Invoke-Required "Web" "JavaScript syntax" {
    Invoke-CommandText "node --check apps/web/src/main.js"
    "apps/web/src/main.js parsed"
  }

  Invoke-Required "1. Console" "Build" {
    Invoke-CommandText 'dotnet build "ui\console\ConsoleValidation.csproj" -v:minimal'
  }

  Invoke-Required "1. Console" "Runtime fallback and logging" {
    $output = Invoke-Expression 'dotnet run --project "ui\console\ConsoleValidation.csproj"' 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
      throw $output
    }
    if ($output -notmatch "Semantic Kernel" -or $output -notmatch "Ollama") {
      throw "Console output did not include Semantic Kernel and Ollama summary."
    }
    "Console emitted Semantic Kernel/Ollama summary"
  }

  Invoke-Required "2. API" "Build" {
    Invoke-CommandText 'dotnet build "ui\api\AspNetAiApi.csproj" -v:minimal'
  }

  Invoke-Required "3. WPF" "Build" {
    Invoke-CommandText 'dotnet build "ui\wpf\WpfDesktopMvp.csproj" -v:minimal'
  }

  Invoke-Required "ONNX Probe" "Offline build and runtime" {
    Invoke-CommandText 'dotnet build "runtime\dotnet\onnx-probe\OnnxRuntimeProbe.csproj" -v:minimal'
    $output = Invoke-CommandText 'dotnet run --project "runtime\dotnet\onnx-probe\OnnxRuntimeProbe.csproj"'
    if ($output -notmatch "ONNX Runtime") {
      throw "ONNX probe did not report status."
    }
    "ONNX probe runs without NuGet restore"
  }

  Invoke-Required "2. API" "Endpoint smoke test" {
    $outPath = Join-Path $RepoRoot "verify-api.out.log"
    $errPath = Join-Path $RepoRoot "verify-api.err.log"
    Remove-Item -LiteralPath $outPath, $errPath -ErrorAction SilentlyContinue

    $apiArgs = 'run --project "ui\api\AspNetAiApi.csproj" --no-build'
    $api = Start-Process -FilePath "dotnet" `
      -ArgumentList $apiArgs `
      -WorkingDirectory $RepoRoot `
      -WindowStyle Hidden `
      -RedirectStandardOutput $outPath `
      -RedirectStandardError $errPath `
      -PassThru

    try {
      $health = Wait-Api
      if ($health.status -ne "ok") { throw "Health status was not ok." }

      $models = Invoke-RestMethod -Uri "http://localhost:$ApiPort/api/models"
      if (-not $models.models) { throw "Models endpoint returned no fallback model." }

      $session = Invoke-JsonPost "/api/session/new" @{ title = "verify" }
      if (-not $session.sessionId) { throw "Session endpoint returned no sessionId." }

      $chat = Invoke-JsonPost "/api/chat" @{ sessionId = $session.sessionId; model = "llama3.2"; message = "verify chat" }
      if (-not $chat.response) { throw "Chat endpoint returned no response." }

      $rag = Invoke-JsonPost "/api/rag/search" @{ query = "ASP.NET API"; topK = 2 }
      if (-not $rag.results) { throw "RAG endpoint returned no results." }

      $tool = Invoke-JsonPost "/api/tools/execute" @{ name = "time"; input = "" }
      if ($tool.success -ne $true) { throw "Tool endpoint failed." }

      $streamBody = @{ sessionId = $session.sessionId; model = "llama3.2"; message = "verify stream" } | ConvertTo-Json
      $stream = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:$ApiPort/api/chat/stream" -Method Post -ContentType "application/json" -Body $streamBody
      if ($stream.StatusCode -ne 200 -or $stream.Content -notmatch "data:") {
        throw "Stream endpoint did not return SSE data."
      }

      "health/models/session/chat/rag/tools/stream passed"
    }
    finally {
      if ($api -and -not $api.HasExited) {
        Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
      }
      Remove-Item -LiteralPath $outPath, $errPath -ErrorAction SilentlyContinue
    }
  }

  Invoke-Optional "4. WinUI" "Template availability" {
    $output = dotnet new list winui 2>&1
    if ($LASTEXITCODE -ne 0) {
      throw "WinUI template is not installed; scaffold is expected under ui\winui."
    }
    "WinUI template installed"
  }

  Invoke-Required "4. WinUI" "Scaffold files" {
    foreach ($path in @(
      "ui\winui\App.xaml",
      "ui\winui\MainWindow.xaml",
      "ui\winui\WinUiApiClient.cs",
      "ui\winui\README.md"
    )) {
      if (-not (Test-Path -LiteralPath $path)) { throw "Missing $path" }
    }
    "WinUI scaffold files present"
  }

  Invoke-Optional "5. Avalonia" "Template availability" {
    $output = dotnet new list avalonia 2>&1
    if ($LASTEXITCODE -ne 0) {
      throw "Avalonia template is not installed; scaffold is expected under ui\avalonia."
    }
    "Avalonia template installed"
  }

  Invoke-Required "5. Avalonia" "Scaffold files" {
    foreach ($path in @(
      "ui\avalonia\App.axaml",
      "ui\avalonia\MainWindow.axaml",
      "ui\avalonia\AvaloniaApiClient.cs",
      "ui\avalonia\README.md"
    )) {
      if (-not (Test-Path -LiteralPath $path)) { throw "Missing $path" }
    }
    "Avalonia scaffold files present"
  }

  Invoke-Required "Discovery" "Generated .NET data" {
    Invoke-CommandText 'powershell -ExecutionPolicy Bypass -File scripts\sync-dotnet-ai.ps1'
    $content = Get-Content -Raw -Encoding UTF8 "apps/web/src/dotnet-ai.generated.js"
    foreach ($name in @("Console Validation", "ASP.NET API", "WPF Desktop MVP", "WinUI Modern UI", "Avalonia CrossPlatform UI")) {
      if ($content -notmatch [regex]::Escape($name)) { throw "Generated data missing $name" }
    }
    "all expected .NET entries generated"
  }
}
finally {
  Pop-Location
}

Write-Host ""
Write-Host "Verification summary:"
$Results | ForEach-Object {
  Write-Host ("- {0} | {1} | {2}" -f $_.status, $_.stage, $_.name)
}

if ($Failures -gt 0) {
  Write-Host ""
  Write-Host "$Failures required verification step(s) failed."
  exit 1
}

Write-Host ""
Write-Host "Required verification passed. Optional template warnings are acceptable until templates are installed."
