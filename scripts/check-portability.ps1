param(
  [switch]$RunBuild,
  [switch]$RunLauncher,
  [int]$SmokeTestPort = 5096
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$NuGetConfig = Join-Path $RepoRoot "NuGet.Config"
$BuildPublishScript = Join-Path $RepoRoot "scripts\build-publish.ps1"
$LauncherScript = Join-Path $RepoRoot "publish\start-local-ai.ps1"
$ApiPublishRoot = Join-Path $RepoRoot "publish\app\api"
$WpfPublishRoot = Join-Path $RepoRoot "publish\app\wpf"
$Failures = 0

function Add-Result {
  param(
    [string]$Status,
    [string]$Name,
    [string]$Detail
  )

  Write-Host "[$Status] $Name :: $Detail"
  if ($Status -eq "FAIL") {
    $script:Failures += 1
  }
}

function Test-RequiredFile {
  param([string]$Path)

  if (Test-Path -LiteralPath $Path -PathType Leaf) {
    Add-Result "PASS" "file" $Path
    return
  }

  Add-Result "FAIL" "file" "missing: $Path"
}

function Test-TextContains {
  param(
    [string]$Path,
    [string]$Pattern,
    [string]$Name
  )

  $content = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop
  if ($content -match $Pattern) {
    Add-Result "PASS" $Name $Pattern
    return
  }

  Add-Result "FAIL" $Name "pattern not found: $Pattern"
}

function Test-NoTargetFramework10 {
  $matches = Get-ChildItem -LiteralPath $RepoRoot -Recurse -File -Filter *.csproj |
    Where-Object { $_.FullName -notmatch "[\\/](bin|obj|publish)[\\/]" } |
    Select-String -Pattern "<TargetFramework>net10\.0"

  if ($matches) {
    Add-Result "FAIL" "target frameworks" (($matches | ForEach-Object { $_.Path }) -join "; ")
    return
  }

  Add-Result "PASS" "target frameworks" "no net10.0 project targets"
}

function Test-NuGetConfig {
  Test-RequiredFile $NuGetConfig
  if (-not (Test-Path -LiteralPath $NuGetConfig -PathType Leaf)) {
    return
  }

  [xml]$config = Get-Content -LiteralPath $NuGetConfig -Raw
  $sources = @($config.configuration.packageSources.add)
  $hasClear = $null -ne $config.configuration.packageSources.clear
  $onlyNugetOrg = $sources.Count -eq 1 -and $sources[0].key -eq "nuget.org" -and $sources[0].value -eq "https://api.nuget.org/v3/index.json"

  if ($hasClear -and $onlyNugetOrg) {
    Add-Result "PASS" "NuGet sources" "repo config clears inherited machine-specific sources"
  }
  else {
    Add-Result "FAIL" "NuGet sources" "NuGet.Config must clear inherited sources and use nuget.org"
  }

  if (Get-Command dotnet -ErrorAction SilentlyContinue) {
    $output = & dotnet nuget list source --configfile $NuGetConfig 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0 -and $output -match "nuget\.org" -and $output -notmatch "SynologyDrive") {
      Add-Result "PASS" "NuGet effective sources" "only repo-configured sources are visible"
    }
    else {
      Add-Result "FAIL" "NuGet effective sources" $output.Trim()
    }
  }
  else {
    Add-Result "WARN" "dotnet" "SDK not installed; source build cannot run on this PC"
  }
}

function Test-PublishOutput {
  $apiExe = Join-Path $ApiPublishRoot "AspNetAiApi.exe"
  $apiDll = Join-Path $ApiPublishRoot "AspNetAiApi.dll"
  $apiRuntimeConfig = Join-Path $ApiPublishRoot "AspNetAiApi.runtimeconfig.json"
  $apiWebIndex = Join-Path $ApiPublishRoot "wwwroot\index.html"
  $coreLib = Join-Path $ApiPublishRoot "System.Private.CoreLib.dll"

  if ((Test-Path -LiteralPath $apiExe -PathType Leaf) -and
      (Test-Path -LiteralPath $apiDll -PathType Leaf) -and
      (Test-Path -LiteralPath $apiRuntimeConfig -PathType Leaf) -and
      (Test-Path -LiteralPath $apiWebIndex -PathType Leaf)) {
    Add-Result "PASS" "API publish output" $ApiPublishRoot
  }
  else {
    Add-Result "WARN" "API publish output" "missing output; first run will need a .NET 9+ SDK build"
    return
  }

  $runtimeConfig = Get-Content -LiteralPath $apiRuntimeConfig -Raw | ConvertFrom-Json
  if ($runtimeConfig.runtimeOptions.tfm -eq "net9.0") {
    Add-Result "PASS" "API target framework" "net9.0"
  }
  else {
    Add-Result "FAIL" "API target framework" $runtimeConfig.runtimeOptions.tfm
  }

  if ((Test-Path -LiteralPath $coreLib -PathType Leaf) -and $runtimeConfig.runtimeOptions.includedFrameworks) {
    Add-Result "PASS" "API self-contained" "runtime payload included"
  }
  else {
    Add-Result "WARN" "API self-contained" "framework-dependent output requires .NET runtime on target PC"
  }

  $wpfExe = Join-Path $WpfPublishRoot "WpfDesktopMvp.exe"
  $wpfRuntimeConfig = Join-Path $WpfPublishRoot "WpfDesktopMvp.runtimeconfig.json"
  if ((Test-Path -LiteralPath $wpfExe -PathType Leaf) -and (Test-Path -LiteralPath $wpfRuntimeConfig -PathType Leaf)) {
    Add-Result "PASS" "WPF publish output" $WpfPublishRoot
  }
  else {
    Add-Result "WARN" "WPF publish output" "missing desktop output; launcher will skip WPF"
  }
}

Push-Location $RepoRoot
try {
  Test-NuGetConfig
  Test-NoTargetFramework10
  Test-TextContains -Path $BuildPublishScript -Pattern "--configfile" -Name "build-publish NuGet isolation"
  Test-TextContains -Path $BuildPublishScript -Pattern "NUGET_PACKAGES" -Name "build-publish package cache isolation"
  Test-TextContains -Path $LauncherScript -Pattern "RefreshPublish" -Name "launcher explicit refresh"
  Test-TextContains -Path $LauncherScript -Pattern "using existing publish output" -Name "launcher prefers publish output"
  Test-PublishOutput

  if ($RunBuild) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $BuildPublishScript -IncludeWpf
    if ($LASTEXITCODE -eq 0) {
      Add-Result "PASS" "build-publish" "self-contained publish regenerated"
    }
    else {
      Add-Result "FAIL" "build-publish" "publish script failed"
    }
  }

  if ($RunLauncher) {
    try {
      & powershell -NoProfile -ExecutionPolicy Bypass -File $LauncherScript -NoWpf -NoWeb -ApiPort $SmokeTestPort -ApiStartupTimeoutSeconds 30
      if ($LASTEXITCODE -ne 0) {
        Add-Result "FAIL" "launcher" "launcher failed"
      }
      else {
        $ready = Invoke-RestMethod -Uri "http://localhost:$SmokeTestPort/api/ready" -TimeoutSec 5
        if ($ready.status -eq "ready") {
          Add-Result "PASS" "launcher" "API reached ready state on port $SmokeTestPort"
        }
        else {
          Add-Result "FAIL" "launcher" "unexpected ready response"
        }
      }
    }
    finally {
      Get-Process AspNetAiApi -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($RepoRoot, [StringComparison]::OrdinalIgnoreCase) } |
        Stop-Process -Force -ErrorAction SilentlyContinue
    }
  }
}
finally {
  Pop-Location
}

if ($Failures -gt 0) {
  Write-Host ""
  Write-Host "$Failures portability check(s) failed."
  exit 1
}

Write-Host ""
Write-Host "Portability checks passed. WARN entries describe optional or environment-dependent capabilities."
