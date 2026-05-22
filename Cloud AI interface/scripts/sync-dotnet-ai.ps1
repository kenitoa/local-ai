param(
  [string]$DotnetFilesPath = "ui",
  [string]$OutputPath = "apps/web/src/dotnet-ai.generated.js",
  [switch]$Watch
)

$ErrorActionPreference = "Stop"

function New-Slug {
  param([string]$Value)

  $slug = $Value.ToLowerInvariant() -replace '[^a-z0-9]+', '-'
  $slug = $slug.Trim('-')
  if ([string]::IsNullOrWhiteSpace($slug)) {
    return "dotnet-ai"
  }

  return $slug
}

function Get-FirstFile {
  param(
    [System.IO.DirectoryInfo]$Folder,
    [string]$Pattern
  )

  return Get-ChildItem -LiteralPath $Folder.FullName -Recurse -File -Filter $Pattern -ErrorAction SilentlyContinue |
    Select-Object -First 1
}

function Get-RelativeDisplayPath {
  param(
    [string]$BasePath,
    [string]$ChildPath
  )

  if ([string]::IsNullOrWhiteSpace($ChildPath)) {
    return ""
  }

  $base = [System.IO.Path]::GetFullPath($BasePath)
  $child = [System.IO.Path]::GetFullPath($ChildPath)
  if ($child.StartsWith($base, [System.StringComparison]::OrdinalIgnoreCase)) {
    return $child.Substring($base.Length).TrimStart('\', '/')
  }

  return $child
}

function Read-Manifest {
  param([System.IO.DirectoryInfo]$Folder)

  $manifestPath = Join-Path $Folder.FullName "dotnet-ai.json"
  if (-not (Test-Path -LiteralPath $manifestPath)) {
    return $null
  }

  try {
    return Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
  }
  catch {
    return $null
  }
}

function New-Check {
  param(
    [string]$Label,
    [bool]$Passed,
    [string]$OkDetail,
    [string]$WaitDetail
  )

  return [ordered]@{
    label = $Label
    state = if ($Passed) { "ok" } else { "wait" }
    detail = if ($Passed) { $OkDetail } else { $WaitDetail }
  }
}

function Convert-DotnetFolder {
  param(
    [System.IO.DirectoryInfo]$Folder
  )

  $manifest = Read-Manifest -Folder $Folder
  $exe = Get-FirstFile -Folder $Folder -Pattern "*.exe"
  $dll = Get-FirstFile -Folder $Folder -Pattern "*.dll"
  $csproj = Get-FirstFile -Folder $Folder -Pattern "*.csproj"
  $runtimeConfig = Get-FirstFile -Folder $Folder -Pattern "*.runtimeconfig.json"
  $deps = Get-FirstFile -Folder $Folder -Pattern "*.deps.json"
  $appSettings = Get-FirstFile -Folder $Folder -Pattern "appsettings*.json"

  $launchFile = $exe
  if ($null -eq $launchFile) { $launchFile = $dll }
  if ($null -eq $launchFile) { $launchFile = $csproj }

  $displayName = $Folder.Name
  if ($null -ne $manifest -and -not [string]::IsNullOrWhiteSpace($manifest.name)) {
    $displayName = [string]$manifest.name
  }

  $version = "folder"
  if ($null -ne $manifest -and -not [string]::IsNullOrWhiteSpace($manifest.version)) {
    $version = [string]$manifest.version
  }
  elseif ($null -ne $runtimeConfig) {
    $version = "runtimeconfig"
  }
  elseif ($null -ne $csproj) {
    $version = "source"
  }

  $model = "Local .NET"
  if ($null -ne $manifest -and -not [string]::IsNullOrWhiteSpace($manifest.model)) {
    $model = [string]$manifest.model
  }

  $purpose = "Local .NET AI source under ui."
  if ($null -ne $manifest -and -not [string]::IsNullOrWhiteSpace($manifest.purpose)) {
    $purpose = [string]$manifest.purpose
  }

  $specialty = "Local .NET AI folder"
  if ($null -ne $manifest -and -not [string]::IsNullOrWhiteSpace($manifest.specialty)) {
    $specialty = [string]$manifest.specialty
  }

  $memory = "Folder package"
  if ($null -ne $manifest -and -not [string]::IsNullOrWhiteSpace($manifest.memory)) {
    $memory = [string]$manifest.memory
  }

  $status = if ($null -ne $launchFile) { "ready" } else { "standby" }
  $launchDetail = if ($null -ne $launchFile) {
    Get-RelativeDisplayPath -BasePath $Folder.FullName -ChildPath $launchFile.FullName
  }
  else {
    "No .exe, .dll, or .csproj found"
  }

  return [ordered]@{
    id = "folder-$(New-Slug $Folder.Name)"
    name = $displayName
    runtime = ".NET folder"
    status = $status
    enabled = $true
    installed = $true
    installPath = $Folder.FullName
    model = $model
    version = $version
    memory = $memory
    specialty = $specialty
    route = "ui/$($Folder.Name)"
    purpose = $purpose
    checks = @(
      [ordered]@{ label = "Folder detected"; state = "ok"; detail = $Folder.FullName },
      (New-Check -Label "Launch file" -Passed ($null -ne $launchFile) -OkDetail $launchDetail -WaitDetail "Add a runnable .exe, .dll, or .csproj"),
      (New-Check -Label "Runtime config" -Passed ($null -ne $runtimeConfig) -OkDetail (Get-RelativeDisplayPath -BasePath $Folder.FullName -ChildPath $runtimeConfig.FullName) -WaitDetail "No .runtimeconfig.json found"),
      (New-Check -Label "Dependency file" -Passed ($null -ne $deps) -OkDetail (Get-RelativeDisplayPath -BasePath $Folder.FullName -ChildPath $deps.FullName) -WaitDetail "No .deps.json found"),
      (New-Check -Label "App settings" -Passed ($null -ne $appSettings) -OkDetail (Get-RelativeDisplayPath -BasePath $Folder.FullName -ChildPath $appSettings.FullName) -WaitDetail "No appsettings*.json found")
    )
  }
}

function Write-DotnetAiData {
  param(
    [string]$RootPath,
    [string]$TargetPath
  )

  New-Item -ItemType Directory -Force -Path $RootPath | Out-Null

  $items = @()
  $folders = Get-ChildItem -LiteralPath $RootPath -Directory -ErrorAction SilentlyContinue | Sort-Object Name
  foreach ($folder in $folders) {
    $items += Convert-DotnetFolder -Folder $folder
  }

  $outputFullPath = Join-Path (Get-Location) $TargetPath
  $outputDir = Split-Path -Parent $outputFullPath
  New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

  if ($items.Count -eq 0) {
    $json = "[]"
  }
  else {
    $jsonItems = @()
    foreach ($item in $items) {
      $jsonItems += ($item | ConvertTo-Json -Depth 8)
    }
    $json = "[$($jsonItems -join ",`n")]"
  }

  $content = @"
// Generated by scripts/sync-dotnet-ai.ps1. Do not edit by hand.
window.discoveredDotnetAis = $json;
"@

  Set-Content -LiteralPath $outputFullPath -Value $content -Encoding UTF8 -Force
  Write-Host "Scanned $DotnetFilesPath and wrote $TargetPath with $($items.Count) .NET folder entries."
}

$rootPath = Join-Path (Get-Location) $DotnetFilesPath
Write-DotnetAiData -RootPath $rootPath -TargetPath $OutputPath

if ($Watch) {
  Write-Host "Watching $DotnetFilesPath for .NET folder changes. Press Ctrl+C to stop."
  $watcher = [System.IO.FileSystemWatcher]::new($rootPath)
  $watcher.IncludeSubdirectories = $true
  $watcher.NotifyFilter = [System.IO.NotifyFilters]'FileName, DirectoryName, LastWrite, CreationTime'
  $watcher.EnableRaisingEvents = $true

  try {
    while ($true) {
      $change = $watcher.WaitForChanged([System.IO.WatcherChangeTypes]::All, 1000)
      if ($change.TimedOut) {
        continue
      }

      Start-Sleep -Milliseconds 700
      Write-DotnetAiData -RootPath $rootPath -TargetPath $OutputPath
    }
  }
  finally {
    $watcher.Dispose()
  }
}
