param(
    [string]$Model = "llama3.1",
    [string]$EmbedModel = "embeddinggemma",
    [string]$Endpoint = "http://localhost:11434",
    [switch]$SkipEmbedding,
    [switch]$SkipOpenAICompatible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Endpoint = $Endpoint.TrimEnd("/")

function Invoke-OllamaJson {
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body = $null
    )

    $uri = "$Endpoint$Path"
    if ($null -eq $Body) {
        return Invoke-RestMethod -Uri $uri -Method $Method -TimeoutSec 60
    }

    $json = $Body | ConvertTo-Json -Depth 12
    return Invoke-RestMethod -Uri $uri -Method $Method -Body $json -ContentType "application/json" -TimeoutSec 120
}

Write-Host "Ollama API test"
Write-Host "Endpoint: $Endpoint"
Write-Host "Model: $Model"
Write-Host ""

Write-Host "GET /api/tags"
$tags = Invoke-OllamaJson -Method Get -Path "/api/tags"
$installed = @()
if ($tags.models) {
    $installed = @($tags.models | ForEach-Object { $_.name })
}

if ($installed.Count -eq 0) {
    Write-Host "No installed models were returned." -ForegroundColor Yellow
}
else {
    $installed | ForEach-Object { Write-Host "- $_" }
}

$modelNames = @($Model, "$Model`:latest")
$modelInstalled = $false
foreach ($name in $modelNames) {
    if ($installed -contains $name) {
        $modelInstalled = $true
        break
    }
}

if (-not $modelInstalled) {
    throw "Model '$Model' was not found in /api/tags. Install it first with: ollama pull $Model"
}

Write-Host ""
Write-Host "POST /api/chat"
$chat = Invoke-OllamaJson -Method Post -Path "/api/chat" -Body @{
    model = $Model
    stream = $false
    messages = @(
        @{
            role = "system"
            content = "너는 한국어로 답하는 로컬 AI 비서다."
        }
        @{
            role = "user"
            content = "Ollama가 뭔지 짧게 설명해줘."
        }
    )
}
Write-Host $chat.message.content

if (-not $SkipOpenAICompatible) {
    Write-Host ""
    Write-Host "POST /v1/chat/completions"
    $completion = Invoke-OllamaJson -Method Post -Path "/v1/chat/completions" -Body @{
        model = $Model
        messages = @(
            @{
                role = "user"
                content = "안녕. 한 문장으로 답해줘."
            }
        )
    }

    if ($completion.choices -and $completion.choices.Count -gt 0) {
        Write-Host $completion.choices[0].message.content
    }
    else {
        Write-Host "OpenAI-compatible response returned no choices." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "POST /api/generate"
$generate = Invoke-OllamaJson -Method Post -Path "/api/generate" -Body @{
    model = $Model
    stream = $false
    prompt = "Say hello in one short sentence."
}
Write-Host $generate.response

if (-not $SkipEmbedding) {
    Write-Host ""
    Write-Host "POST /api/embed"
    try {
        $embed = Invoke-OllamaJson -Method Post -Path "/api/embed" -Body @{
            model = $EmbedModel
            input = "local ai"
        }

        $count = 0
        if ($embed.embeddings -and $embed.embeddings.Count -gt 0) {
            $count = $embed.embeddings[0].Count
        }

        Write-Host "Embedding dimensions: $count"
    }
    catch {
        Write-Host "Embedding test skipped or failed. Install an embedding model first, for example: ollama pull embeddinggemma" -ForegroundColor Yellow
        Write-Host $_.Exception.Message
    }
}

Write-Host ""
Write-Host "Verification target"
Write-Host "- Ollama server: reachable"
Write-Host "- Port 11434: responding"
Write-Host "- modelId: $Model installed"
Write-Host "- /api/chat: working"
if (-not $SkipOpenAICompatible) {
    Write-Host "- /v1/chat/completions: working"
}

Write-Host ""
Write-Host "API test completed." -ForegroundColor Green
