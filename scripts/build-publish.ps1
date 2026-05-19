param(
  [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$PublishRoot = Join-Path $RepoRoot "publish"
$AppRoot = Join-Path $PublishRoot "app"
$ApiOut = Join-Path $AppRoot "api"
$WpfOut = Join-Path $AppRoot "wpf"

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
    -v:minimal
}

Push-Location $RepoRoot
try {
  New-Item -ItemType Directory -Force -Path $PublishRoot | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $PublishRoot "logs") | Out-Null

  Invoke-DotnetPublish -Project "ui\api\AspNetAiApi.csproj" -Output $ApiOut
  Invoke-DotnetPublish -Project "ui\wpf\WpfDesktopMvp.csproj" -Output $WpfOut

  Write-Host ""
  Write-Host "Publish output is ready:"
  Write-Host "- $ApiOut"
  Write-Host "- $WpfOut"
  Write-Host ""
  Write-Host "Run: publish\start-local-ai.cmd"
}
finally {
  Pop-Location
}
