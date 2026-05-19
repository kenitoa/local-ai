param(
    [string]$ModelId,
    [string]$Endpoint,
    [string]$ReportPath = (Join-Path $PSScriptRoot "final-validation-report.json"),
    [switch]$SkipBuild,
    [switch]$Strict
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\ollama-env.ps1"

function Get-RepoRoot {
    $current = $PSScriptRoot
    while ($current) {
        if (Test-Path -LiteralPath (Join-Path $current ".git")) {
            return $current
        }

        $parent = Split-Path -Parent $current
        if ($parent -eq $current) {
            break
        }

        $current = $parent
    }

    return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
}

function Read-DotEnv {
    param([string]$Path)

    $map = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $map
    }

    Get-Content -Encoding UTF8 -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }

        $separatorIndex = $line.IndexOf("=")
        if ($separatorIndex -lt 1) {
            return
        }

        $name = $line.Substring(0, $separatorIndex).Trim()
        $value = $line.Substring($separatorIndex + 1).Trim().Trim('"').Trim("'")
        $map[$name] = $value
    }

    return $map
}

function Resolve-RepoPath {
    param(
        [string]$PathValue,
        [string]$RepoRoot
    )

    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return $PathValue
    }

    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }

    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $PathValue))
}

function Add-Check {
    param(
        [System.Collections.Generic.List[object]]$Checks,
        [string]$Area,
        [string]$Name,
        [string]$Status,
        [string]$Message
    )

    $Checks.Add([pscustomobject][ordered]@{
        area = $Area
        name = $Name
        status = $Status
        message = $Message
    })
}

function Test-ModelName {
    param(
        [string[]]$InstalledModels,
        [string]$Name
    )

    return $InstalledModels | Where-Object {
        $_.Equals($Name, [StringComparison]::OrdinalIgnoreCase) -or
        $_.StartsWith("$Name`:", [StringComparison]::OrdinalIgnoreCase)
    } | Select-Object -First 1
}

$repoRoot = Get-RepoRoot
$envPath = Join-Path $repoRoot ".env"
$envValues = Read-DotEnv -Path $envPath
$apiSettingsPath = Join-Path $repoRoot "runtime/semantic-kernel\LocalAI.Api\appsettings.json"
$checks = [System.Collections.Generic.List[object]]::new()
$ollamaCli = Resolve-OllamaCli -EnvValues $envValues -RepoRoot $repoRoot

$apiSettings = $null
if (Test-Path -LiteralPath $apiSettingsPath) {
    $apiSettings = Get-Content -Encoding UTF8 -LiteralPath $apiSettingsPath | ConvertFrom-Json
}

if (-not $ModelId) {
    $ModelId = if ($apiSettings) { $apiSettings.Ollama.ModelId } else { "local-assistant" }
}

if (-not $Endpoint) {
    $Endpoint = if ($apiSettings) { $apiSettings.Ollama.Endpoint } else { "http://localhost:11434" }
}

$endpointBase = $Endpoint.TrimEnd("/")

Write-Host "Final implementation validation"
Write-Host "Repo: $repoRoot"
Write-Host "Endpoint: $endpointBase"
Write-Host "ModelId: $ModelId"
Write-Host ""

# 1-2. Ollama install/version
if ($ollamaCli) {
    Add-Check $checks "1-2" "Ollama CLI" "pass" "local ollama found: $ollamaCli"
    try {
        $version = (& $ollamaCli --version 2>&1 | Out-String).Trim()
        Add-Check $checks "1-2" "ollama --version" "pass" $version
    }
    catch {
        Add-Check $checks "1-2" "ollama --version" "fail" $_.Exception.Message
    }
}
else {
    $cliValue = if ($envValues.ContainsKey("OLLAMA_CLI")) { $envValues["OLLAMA_CLI"] } else { "runtime\ollama\server\cli\ollama.exe" }
    Add-Check $checks "1-2" "Ollama CLI" "fail" "Local ollama.exe was not found. Expected: $(Resolve-RepoPath -PathValue $cliValue -RepoRoot $repoRoot). Run install-ollama.ps1."
}

# 3-4. Model files and selected pull list
$selectedModelsPath = Join-Path $PSScriptRoot "models.selected.txt"
if (Test-Path -LiteralPath $selectedModelsPath) {
    $selectedModels = @(Get-Content -Encoding UTF8 -LiteralPath $selectedModelsPath | Where-Object { $_ -and -not $_.StartsWith("#") })
    Add-Check $checks "3" "Selected model list" "pass" "models.selected.txt contains $($selectedModels.Count) model(s): $($selectedModels -join ', ')"
}
else {
    Add-Check $checks "3" "Selected model list" "fail" "models.selected.txt is missing."
}

$modelfilePath = Join-Path $PSScriptRoot "Modelfile"
if (Test-Path -LiteralPath $modelfilePath) {
    $modelfile = Get-Content -Encoding UTF8 -LiteralPath $modelfilePath
    $hasFrom = @($modelfile | Where-Object { $_ -match "^\s*FROM\s+" }).Count -gt 0
    $hasNumCtx = @($modelfile | Where-Object { $_ -match "^\s*PARAMETER\s+num_ctx\s+\d+" }).Count -gt 0
    $hasSystem = @($modelfile | Where-Object { $_ -match "^\s*SYSTEM\s+" }).Count -gt 0

    if ($hasFrom -and $hasNumCtx -and $hasSystem) {
        Add-Check $checks "11" "Modelfile" "pass" "Modelfile contains FROM, PARAMETER num_ctx, and SYSTEM."
    }
    else {
        Add-Check $checks "11" "Modelfile" "fail" "Modelfile is missing FROM, PARAMETER num_ctx, or SYSTEM."
    }
}
else {
    Add-Check $checks "11" "Modelfile" "fail" "Modelfile is missing."
}

# 5-6. Server tags/chat
$serverReachable = $false
$installedModels = @()
try {
    $tags = Invoke-RestMethod -Uri "$endpointBase/api/tags" -Method Get -TimeoutSec 5
    $serverReachable = $true
    if ($tags.models) {
        $installedModels = @($tags.models | ForEach-Object { $_.name })
    }
    Add-Check $checks "5" "/api/tags" "pass" "Server reachable. Installed models: $($installedModels -join ', ')"
}
catch {
    Add-Check $checks "5" "/api/tags" "fail" "Server is not reachable: $($_.Exception.Message)"
}

if ($serverReachable) {
    if (Test-ModelName -InstalledModels $installedModels -Name $ModelId) {
        Add-Check $checks "4,6,12,16" "Configured model installed" "pass" "$ModelId exists in /api/tags."

        try {
            $body = @{
                model = $ModelId
                stream = $false
                messages = @(
                    @{
                        role = "user"
                        content = "한 문장으로 상태 확인이라고 답해줘."
                    }
                )
            } | ConvertTo-Json -Depth 8
            $chat = Invoke-RestMethod -Uri "$endpointBase/api/chat" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 60
            $content = if ($chat.message.content) { $chat.message.content } else { "response received" }
            Add-Check $checks "6" "/api/chat" "pass" $content
        }
        catch {
            Add-Check $checks "6" "/api/chat" "fail" $_.Exception.Message
        }
    }
    else {
        Add-Check $checks "4,6,12,16" "Configured model installed" "fail" "$ModelId is not installed. Run create-custom-model.ps1 or ollama create $ModelId -f Modelfile."
        Add-Check $checks "6" "/api/chat" "skip" "Skipped because configured model is missing."
    }
}
else {
    Add-Check $checks "6" "/api/chat" "skip" "Skipped because Ollama server is not reachable."
}

# 7, 12, 13, 14. Semantic Kernel config/build/health code
if ($apiSettings) {
    $endpointOk = $apiSettings.Ollama.Endpoint -eq "http://localhost:11434" -and
        $apiSettings.AiModel.Endpoint -eq "http://localhost:11434"
    $modelOk = $apiSettings.Ollama.ModelId -eq $ModelId -and
        $apiSettings.AiModel.ModelId -eq $ModelId

    $configStatus = if ($endpointOk -and $modelOk) { "pass" } else { "fail" }
    Add-Check $checks "7,12" "Semantic Kernel endpoint/model config" $configStatus "Endpoint=$($apiSettings.Ollama.Endpoint), ModelId=$($apiSettings.Ollama.ModelId)"
}
else {
    Add-Check $checks "7,12" "Semantic Kernel appsettings" "fail" "appsettings.json is missing."
}

$connectorPath = Join-Path $repoRoot "runtime\ollama\connector\SemanticKernelOllamaConnector.cs"
$connectorText = if (Test-Path -LiteralPath $connectorPath) { Get-Content -Encoding UTF8 -Raw -LiteralPath $connectorPath } else { "" }
if ($connectorText -match "CheckHealthAsync" -and $connectorText -match "JsonDocument" -and $connectorText -match "HasModelAsync") {
    Add-Check $checks "13,14,15,16" "Connector health/model checks" "pass" "JSON parsing health and model checks are implemented."
}
else {
    Add-Check $checks "13,14,15,16" "Connector health/model checks" "fail" "CheckHealthAsync, HasModelAsync, or JsonDocument parsing is missing."
}

if (-not $SkipBuild) {
    $solutionPath = Join-Path $repoRoot "runtime/semantic-kernel\LocalAI.sln"
    try {
        $buildOutput = & dotnet build $solutionPath --no-restore -v:minimal 2>&1
        if ($LASTEXITCODE -eq 0) {
            Add-Check $checks "7,13,14" ".NET build" "pass" "LocalAI.sln builds successfully."
        }
        else {
            Add-Check $checks "7,13,14" ".NET build" "fail" ($buildOutput | Out-String).Trim()
        }
    }
    catch {
        Add-Check $checks "7,13,14" ".NET build" "fail" $_.Exception.Message
    }
}
else {
    Add-Check $checks "7,13,14" ".NET build" "skip" "Skipped by -SkipBuild."
}

# 8-10. Environment, models path, host/firewall/security
$modelsValue = if ($envValues.ContainsKey("OLLAMA_MODELS")) { $envValues["OLLAMA_MODELS"] } else { "" }
$modelsPath = Resolve-RepoPath -PathValue $modelsValue -RepoRoot $repoRoot
if ($modelsPath -and (Test-Path -LiteralPath $modelsPath)) {
    Add-Check $checks "8" "OLLAMA_MODELS" "pass" "$modelsValue -> $modelsPath"
}
else {
    Add-Check $checks "8" "OLLAMA_MODELS" "fail" "Path does not exist: $modelsValue"
}

$hostValue = if ($envValues.ContainsKey("OLLAMA_HOST")) { $envValues["OLLAMA_HOST"] } else { "" }
$securityProfile = if ($envValues.ContainsKey("OLLAMA_SECURITY_PROFILE")) { $envValues["OLLAMA_SECURITY_PROFILE"] } else { "" }
$remoteAddresses = if ($envValues.ContainsKey("OLLAMA_ALLOWED_REMOTE_ADDRESSES")) { $envValues["OLLAMA_ALLOWED_REMOTE_ADDRESSES"] } else { "" }
if ($hostValue -eq "127.0.0.1:11434" -or $hostValue -eq "localhost:11434") {
    Add-Check $checks "9,19" "Network exposure" "pass" "localhost-only."
}
elseif ($hostValue -eq "0.0.0.0:11434" -and $remoteAddresses -and $remoteAddresses -ne "Any") {
    Add-Check $checks "9,19" "Network exposure" "warn" "LAN/VPN exposure configured. Firewall must restrict remote addresses: $remoteAddresses"
}
else {
    Add-Check $checks "9,19" "Network exposure" "fail" "Unsafe or incomplete network settings. OLLAMA_HOST=$hostValue, profile=$securityProfile, remote=$remoteAddresses"
}

$firewallRule = Get-NetFirewallRule -DisplayName "Ollama Local Server 11434" -ErrorAction SilentlyContinue
if ($hostValue -eq "0.0.0.0:11434") {
    if ($firewallRule) {
        $addressFilters = @($firewallRule | Get-NetFirewallAddressFilter -ErrorAction SilentlyContinue)
        $remote = @($addressFilters | ForEach-Object { $_.RemoteAddress })
        if ($remote -contains "Any") {
            Add-Check $checks "10,19" "Windows firewall" "fail" "Firewall rule allows Any remote address."
        }
        else {
            Add-Check $checks "10,19" "Windows firewall" "pass" "Firewall rule exists: $($remote -join ', ')"
        }
    }
    else {
        Add-Check $checks "10,19" "Windows firewall" "fail" "LAN binding requires a Windows firewall rule. Run enable-firewall-rule.ps1 as Administrator."
    }
}
else {
    Add-Check $checks "10,19" "Windows firewall" "pass" "No inbound firewall rule required for localhost-only binding."
}

# 15. Startup task
$task = Get-ScheduledTask -TaskName "Ollama Local Server" -ErrorAction SilentlyContinue
if ($task) {
    Add-Check $checks "15" "Startup task" "pass" "Scheduled task exists. State=$($task.State)"
}
else {
    Add-Check $checks "15" "Startup task" "warn" "Scheduled task is not registered. Run register-startup-task.ps1 when ready."
}

# 16. Performance/context
$contextValue = if ($envValues.ContainsKey("OLLAMA_CONTEXT_LENGTH")) { $envValues["OLLAMA_CONTEXT_LENGTH"] } else { "" }
if ($contextValue -match "^\d+$") {
    Add-Check $checks "16" "OLLAMA_CONTEXT_LENGTH" "pass" "OLLAMA_CONTEXT_LENGTH=$contextValue"
}
else {
    Add-Check $checks "16" "OLLAMA_CONTEXT_LENGTH" "fail" "OLLAMA_CONTEXT_LENGTH is missing or invalid."
}

$benchmarkScript = Join-Path $PSScriptRoot "benchmark-server.ps1"
if (Test-Path -LiteralPath $benchmarkScript) {
    Add-Check $checks "16" "Performance benchmark script" "pass" "benchmark-server.ps1 exists."
}
else {
    Add-Check $checks "16" "Performance benchmark script" "fail" "benchmark-server.ps1 is missing."
}

$summary = [ordered]@{
    pass = @($checks | Where-Object { $_.status -eq "pass" }).Count
    warn = @($checks | Where-Object { $_.status -eq "warn" }).Count
    fail = @($checks | Where-Object { $_.status -eq "fail" }).Count
    skip = @($checks | Where-Object { $_.status -eq "skip" }).Count
}

$report = [ordered]@{
    timestamp = (Get-Date).ToString("o")
    repoRoot = $repoRoot
    endpoint = $endpointBase
    modelId = $ModelId
    summary = $summary
    checks = $checks
}

$report | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $ReportPath

$checks |
    Sort-Object area, name |
    Format-Table area, name, status, message -AutoSize

Write-Host ""
Write-Host "Summary: pass=$($summary.pass), warn=$($summary.warn), fail=$($summary.fail), skip=$($summary.skip)"
Write-Host "Report: $ReportPath"

if ($summary.fail -gt 0) {
    exit 2
}

if ($Strict -and $summary.warn -gt 0) {
    exit 1
}

exit 0
