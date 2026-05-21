param(
  [string]$Configuration = "Release",
  [switch]$IncludeWpf
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$RepoRoot = Split-Path -Parent $PSScriptRoot
$PublishRoot = Join-Path $RepoRoot "publish"
$AppRoot = Join-Path $PublishRoot "app"
$ApiOut = Join-Path $AppRoot "api"
$WpfOut = Join-Path $AppRoot "wpf"
$WebSource = Join-Path $RepoRoot "apps\web"
$WebOut = Join-Path $ApiOut "wwwroot"

function Invoke-DotnetPublish {
  param(
    [string]$Project,
    [string]$Output
  )

  New-Item -ItemType Directory -Force -Path $Output | Out-Null
  dotnet publish $Project `
    -c $Configuration `
    -o $Output `
    --self-contained false `
    --no-restore `
    -v:minimal

  if ($LASTEXITCODE -ne 0) {
    throw "dotnet publish failed for $Project"
  }
}

Push-Location $RepoRoot
try {
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
  Write-Host ""
  Write-Host "Run: publish\start-local-ai.cmd"
}
finally {
  Pop-Location
}
