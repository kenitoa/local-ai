param(
    [Alias("선택")]
    [string[]]$Select,

    [Alias("선택삭제", "선택_삭제")]
    [string[]]$Remove,

    [string[]]$Models,
    [string]$OutputPath = (Join-Path $PSScriptRoot "models.selected.txt"),
    [switch]$IncludeChat,
    [switch]$IncludeCoding,
    [switch]$IncludeEmbeddingRag,
    [switch]$RagMinimal,
    [switch]$Replace,
    [switch]$Clear,
    [switch]$List
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Read-ModelFile {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return @()
    }

    return Get-Content -Encoding UTF8 -LiteralPath $Path |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and -not $_.StartsWith("#") } |
        ForEach-Object { $_ -split "," } |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ }
}

function Save-SelectedModels {
    param(
        [string]$Path,
        [string[]]$ModelsToSave
    )

    $final = @($ModelsToSave | Where-Object { $_ } | Sort-Object -Unique)
    $final | Set-Content -Encoding UTF8 -LiteralPath $Path
    return $final
}

function Add-ModelValues {
    param(
        [System.Collections.Generic.List[string]]$Target,
        [string[]]$Values
    )

    if (-not $Values) {
        return
    }

    foreach ($value in $Values) {
        if ([string]::IsNullOrWhiteSpace($value)) {
            continue
        }

        $value -split "," |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ } |
            ForEach-Object { $Target.Add($_) }
    }
}

function Write-SelectedModels {
    param(
        [string]$Title,
        [string[]]$Items
    )

    $safeItems = @($Items)
    $itemCount = ($safeItems | Measure-Object).Count
    Write-Host $Title
    if ($itemCount -eq 0) {
        Write-Host "- empty"
        return
    }

    $safeItems | ForEach-Object { Write-Host "- $_" }
}

$current = @()
if (-not $Replace -and -not $Clear) {
    $current = @(Read-ModelFile $OutputPath)
}

if ($List) {
    Write-SelectedModels -Title "현재 선택 모델:" -Items $current
    exit 0
}

$toSelect = New-Object System.Collections.Generic.List[string]
$toRemove = New-Object System.Collections.Generic.List[string]

if ($Models) {
    Add-ModelValues -Target $toSelect -Values $Models
}

if ($Select) {
    Add-ModelValues -Target $toSelect -Values $Select
}

if ($Remove) {
    Add-ModelValues -Target $toRemove -Values $Remove
}

if ($IncludeChat) {
    Read-ModelFile (Join-Path $PSScriptRoot "models.chat.txt") | ForEach-Object { $toSelect.Add($_) }
}

if ($IncludeCoding) {
    Read-ModelFile (Join-Path $PSScriptRoot "models.coding.txt") | ForEach-Object { $toSelect.Add($_) }
}

if ($IncludeEmbeddingRag) {
    Read-ModelFile (Join-Path $PSScriptRoot "models.embedding-rag.txt") | ForEach-Object { $toSelect.Add($_) }
}

if ($RagMinimal) {
    Read-ModelFile (Join-Path $PSScriptRoot "models.rag-minimal.txt") | ForEach-Object { $toSelect.Add($_) }
}

if ($Clear) {
    $current = @()
}

$selectedSet = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($model in $current) {
    [void]$selectedSet.Add($model)
}

foreach ($model in $toSelect) {
    [void]$selectedSet.Add($model)
}

foreach ($model in $toRemove) {
    [void]$selectedSet.Remove($model)
    [void]$selectedSet.Remove("$model`:latest")
}

if ($toSelect.Count -eq 0 -and $toRemove.Count -eq 0 -and -not $Clear) {
    throw "No selection change requested. Use -Select, -Remove, -Models, group switches, -Clear, or -List."
}

$final = Save-SelectedModels -Path $OutputPath -ModelsToSave @($selectedSet)

if ($toSelect.Count -gt 0) {
    Write-SelectedModels -Title "선택:" -Items @($toSelect | Sort-Object -Unique)
}

if ($toRemove.Count -gt 0) {
    Write-SelectedModels -Title "선택 삭제:" -Items @($toRemove | Sort-Object -Unique)
}

if ($Clear) {
    Write-Host "선택 목록을 비웠습니다."
}

Write-Host ""
Write-Host "현재 선택 모델 저장 위치: $OutputPath"
Write-SelectedModels -Title "현재 선택 모델:" -Items $final
Write-Host ""
Write-Host "다운로드: .\pull-models.ps1 -ModelFile .\models.selected.txt"
