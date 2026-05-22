param(
  [string]$Configuration = "Release",
  [string]$RuntimeIdentifier = "win-x64",
  [switch]$IncludeWpf,
  [switch]$FrameworkDependent,
  [switch]$NoRestore
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$SourceRoot = Split-Path -Parent $PSScriptRoot
$RepoRoot = Split-Path -Parent $SourceRoot
if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot "publish") -PathType Container)) {
  $RepoRoot = $SourceRoot
}
$PublishRoot = Join-Path $RepoRoot "publish"
$AppRoot = Join-Path $PublishRoot "app"
$ApiOut = Join-Path $AppRoot "api"
$WpfOut = Join-Path $AppRoot "wpf"
$WebSource = Join-Path $SourceRoot "apps\web"
$WebOut = Join-Path $ApiOut "wwwroot"
$NuGetConfig = Join-Path $SourceRoot "NuGet.Config"
$PackageCacheRoot = Join-Path $SourceRoot ".build\nuget-packages"

function Assert-DotnetSdk {
  if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw "The .NET 9 SDK or newer is required to build missing publish output. Install it from https://dotnet.microsoft.com/download and rerun publish\start-local-ai.cmd."
  }

  $sdkLines = & dotnet --list-sdks
  $hasSupportedSdk = $false
  foreach ($line in $sdkLines) {
    if ($line -match '^(\d+)\.') {
      $major = [int]$Matches[1]
      if ($major -ge 9) {
        $hasSupportedSdk = $true
        break
      }
    }
  }

  if (-not $hasSupportedSdk) {
    $installed = if ($sdkLines) { ($sdkLines -join "; ") } else { "none" }
    throw "The .NET 9 SDK or newer is required to build missing publish output. Installed SDKs: $installed. Install the .NET 9 SDK or newer and rerun publish\start-local-ai.cmd."
  }
}

function Invoke-DotnetPublish {
  param(
    [string]$Project,
    [string]$Output
  )

  New-Item -ItemType Directory -Force -Path $Output | Out-Null
  New-Item -ItemType Directory -Force -Path $PackageCacheRoot | Out-Null

  $restoreArgs = @("restore", $Project, "-v:minimal")
  if (Test-Path -LiteralPath $NuGetConfig -PathType Leaf) {
    $restoreArgs += @("--configfile", $NuGetConfig)
  }
  if (-not $FrameworkDependent) {
    $restoreArgs += @("-r", $RuntimeIdentifier)
  }

  $publishArgs = @(
    "publish",
    $Project,
    "-c", $Configuration,
    "-o", $Output,
    "--no-restore",
    "-v:minimal"
  )
  if ($FrameworkDependent) {
    $publishArgs += @("--self-contained", "false")
  }
  else {
    $publishArgs += @("-r", $RuntimeIdentifier, "--self-contained", "true")
  }

  $previousNuGetPackages = $env:NUGET_PACKAGES
  $env:NUGET_PACKAGES = $PackageCacheRoot
  try {
    if (-not $NoRestore) {
      dotnet @restoreArgs
      if ($LASTEXITCODE -ne 0) {
        throw "dotnet restore failed for $Project"
      }
    }

    dotnet @publishArgs
  }
  finally {
    if ($null -eq $previousNuGetPackages) {
      Remove-Item Env:NUGET_PACKAGES -ErrorAction SilentlyContinue
    }
    else {
      $env:NUGET_PACKAGES = $previousNuGetPackages
    }
  }

  if ($LASTEXITCODE -ne 0) {
    throw "dotnet publish failed for $Project"
  }
}

Push-Location $SourceRoot
try {
  Assert-DotnetSdk
  New-Item -ItemType Directory -Force -Path $PublishRoot | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $PublishRoot "logs") | Out-Null

  Invoke-DotnetPublish -Project "ui\api\AspNetAiApi.csproj" -Output $ApiOut
  if ($IncludeWpf) {
    Invoke-DotnetPublish -Project "ui\wpf\WpfDesktopMvp.csproj" -Output $WpfOut
  }

  if (-not (Test-Path -LiteralPath (Join-Path $WebSource "index.html") -PathType Leaf)) {
    throw "Web UI source was not found: $WebSource"
  }

  if (Test-Path -LiteralPath $WebOut) {
    Remove-Item -LiteralPath $WebOut -Recurse -Force
  }

  New-Item -ItemType Directory -Force -Path $WebOut | Out-Null
  Copy-Item -LiteralPath (Join-Path $WebSource "index.html") -Destination $WebOut -Force
  Copy-Item -LiteralPath (Join-Path $WebSource "src") -Destination $WebOut -Recurse -Force

  Write-Host ""
  Write-Host "Publish output is ready:"
  Write-Host "- $ApiOut"
  Write-Host "- $WebOut"
  if ($IncludeWpf) {
    Write-Host "- $WpfOut"
  }
  if ($FrameworkDependent) {
    Write-Host "- mode: framework-dependent"
  }
  else {
    Write-Host "- mode: self-contained ($RuntimeIdentifier)"
  }
  Write-Host ""
  Write-Host "Run: ..\publish\start-local-ai.cmd"
}
finally {
  Pop-Location
}
