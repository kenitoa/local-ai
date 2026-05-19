param(
    [string]$OutputPath = (Join-Path $PSScriptRoot "models.selected.txt"),

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Models
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

& "$PSScriptRoot\select-models.ps1" -Select $Models -OutputPath $OutputPath
