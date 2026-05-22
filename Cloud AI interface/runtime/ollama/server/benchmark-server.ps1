param(
    [string]$Model = "llama3.1",
    [string]$Endpoint = "http://localhost:11434",
    [int]$ConcurrentRequests = 3,
    [int]$TimeoutSeconds = 180,
    [string]$Prompt = "Ollama가 로컬 AI 서버로 어떻게 동작하는지 한국어로 5문장 이내로 설명해줘.",
    [string]$SaveJsonPath = (Join-Path $PSScriptRoot "benchmark-results.json")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Endpoint = $Endpoint.TrimEnd("/")

function Get-HardwareSnapshot {
    try {
        $json = & "$PSScriptRoot\measure-hardware.ps1" -Json | Out-String
        return $json | ConvertFrom-Json
    }
    catch {
        return [ordered]@{
            error = $_.Exception.Message
        }
    }
}

function Get-NvidiaSmiSnapshot {
    $nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if (-not $nvidiaSmi) {
        return [ordered]@{
            available = $false
            reason = "nvidia-smi was not found. This is normal on CPU-only, Intel, AMD, or non-NVIDIA systems."
        }
    }

    try {
        $lines = & nvidia-smi --query-gpu=name,memory.total,memory.used,utilization.gpu --format=csv,noheader,nounits
        $gpus = @()
        foreach ($line in $lines) {
            $parts = $line -split ","
            if ($parts.Count -ge 4) {
                $gpus += [ordered]@{
                    name = $parts[0].Trim()
                    memoryTotalMiB = [int]$parts[1].Trim()
                    memoryUsedMiB = [int]$parts[2].Trim()
                    utilizationPercent = [int]$parts[3].Trim()
                }
            }
        }

        return [ordered]@{
            available = $true
            gpus = $gpus
        }
    }
    catch {
        return [ordered]@{
            available = $false
            reason = $_.Exception.Message
        }
    }
}

function Assert-OllamaReady {
    param(
        [string]$ModelName
    )

    $tagsUrl = "$Endpoint/api/tags"
    try {
        $tags = Invoke-RestMethod -Uri $tagsUrl -Method Get -TimeoutSec 10
    }
    catch {
        throw "Ollama server is not reachable at $tagsUrl. Start it first with .\start-server.ps1 -Background"
    }

    $installed = @()
    if ($tags.models) {
        $installed = @($tags.models | ForEach-Object { $_.name })
    }

    if (-not (($installed -contains $ModelName) -or ($installed -contains "$ModelName`:latest"))) {
        throw "Model '$ModelName' was not found. Install it first with: ollama pull $ModelName"
    }

    return $installed
}

function Invoke-StreamingChatBenchmark {
    param(
        [string]$ModelName,
        [string]$UserPrompt
    )

    Add-Type -AssemblyName System.Net.Http
    $client = [System.Net.Http.HttpClient]::new()
    $client.Timeout = [TimeSpan]::FromSeconds($TimeoutSeconds)

    $body = [ordered]@{
        model = $ModelName
        stream = $true
        messages = @(
            [ordered]@{
                role = "system"
                content = "너는 한국어로 간결하게 답하는 로컬 AI 성능 검증 비서다."
            },
            [ordered]@{
                role = "user"
                content = $UserPrompt
            }
        )
    }

    $json = $body | ConvertTo-Json -Depth 12
    $content = [System.Net.Http.StringContent]::new($json, [System.Text.Encoding]::UTF8, "application/json")
    $requestUri = "$Endpoint/api/chat"
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $firstTokenMs = $null
    $responseText = New-Object System.Text.StringBuilder
    $evalCount = $null
    $evalDurationNs = $null
    $totalDurationNs = $null
    $loadDurationNs = $null

    try {
        $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post, $requestUri)
        $request.Content = $content
        $response = $client.SendAsync($request, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
        [void]$response.EnsureSuccessStatusCode()

        $stream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $reader = [System.IO.StreamReader]::new($stream)

        while (-not $reader.EndOfStream) {
            $line = $reader.ReadLine()
            if ([string]::IsNullOrWhiteSpace($line)) {
                continue
            }

            $chunk = $line | ConvertFrom-Json
            if ($chunk.message -and $chunk.message.content) {
                if ($null -eq $firstTokenMs) {
                    $firstTokenMs = [Math]::Round($stopwatch.Elapsed.TotalMilliseconds, 2)
                }

                [void]$responseText.Append($chunk.message.content)
            }

            if ($chunk.done -eq $true) {
                if ($chunk.PSObject.Properties.Match("eval_count").Count -gt 0) {
                    $evalCount = [int]$chunk.eval_count
                }
                if ($chunk.PSObject.Properties.Match("eval_duration").Count -gt 0) {
                    $evalDurationNs = [double]$chunk.eval_duration
                }
                if ($chunk.PSObject.Properties.Match("total_duration").Count -gt 0) {
                    $totalDurationNs = [double]$chunk.total_duration
                }
                if ($chunk.PSObject.Properties.Match("load_duration").Count -gt 0) {
                    $loadDurationNs = [double]$chunk.load_duration
                }
            }
        }
    }
    finally {
        $stopwatch.Stop()
        $client.Dispose()
    }

    $tokensPerSecond = $null
    if ($evalCount -and $evalDurationNs -and $evalDurationNs -gt 0) {
        $tokensPerSecond = [Math]::Round($evalCount / ($evalDurationNs / 1000000000), 2)
    }

    return [pscustomobject][ordered]@{
        firstTokenLatencyMs = $firstTokenMs
        totalLatencyMs = [Math]::Round($stopwatch.Elapsed.TotalMilliseconds, 2)
        outputTokenCount = $evalCount
        evalDurationMs = if ($evalDurationNs) { [Math]::Round($evalDurationNs / 1000000, 2) } else { $null }
        totalDurationMs = if ($totalDurationNs) { [Math]::Round($totalDurationNs / 1000000, 2) } else { $null }
        loadDurationMs = if ($loadDurationNs) { [Math]::Round($loadDurationNs / 1000000, 2) } else { $null }
        tokensPerSecond = $tokensPerSecond
        responsePreview = $responseText.ToString().Substring(0, [Math]::Min(240, $responseText.Length))
    }
}

function Invoke-ConcurrencyBenchmark {
    param(
        [string]$ModelName,
        [int]$Count
    )

    if ($Count -le 0) {
        return [pscustomobject][ordered]@{
            requested = 0
            succeeded = 0
            failed = 0
            results = @()
        }
    }

    $jobs = @()
    for ($i = 1; $i -le $Count; $i++) {
        $jobs += Start-Job -ArgumentList $Endpoint, $ModelName, $i, $TimeoutSeconds -ScriptBlock {
            param($Endpoint, $ModelName, $Index, $TimeoutSeconds)

            $body = @{
                model = $ModelName
                stream = $false
                messages = @(
                    @{
                        role = "user"
                        content = "동시 요청 테스트 $Index. 한 문장으로 답해줘."
                    }
                )
            } | ConvertTo-Json -Depth 8

            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            try {
                $response = Invoke-RestMethod -Uri "$Endpoint/api/chat" -Method Post -Body $body -ContentType "application/json" -TimeoutSec $TimeoutSeconds
                $sw.Stop()
                [ordered]@{
                    index = $Index
                    ok = $true
                    latencyMs = [Math]::Round($sw.Elapsed.TotalMilliseconds, 2)
                    contentLength = if ($response.message.content) { $response.message.content.Length } else { 0 }
                }
            }
            catch {
                $sw.Stop()
                [ordered]@{
                    index = $Index
                    ok = $false
                    latencyMs = [Math]::Round($sw.Elapsed.TotalMilliseconds, 2)
                    error = $_.Exception.Message
                }
            }
        }
    }

    $completed = Wait-Job -Job $jobs -Timeout ($TimeoutSeconds + 30)
    $timedOut = @($jobs | Where-Object { $_.State -eq "Running" })
    foreach ($job in $timedOut) {
        Stop-Job -Job $job
    }

    $results = @()
    foreach ($job in $jobs) {
        $jobResult = Receive-Job -Job $job -ErrorAction SilentlyContinue
        if ($jobResult) {
            $results += $jobResult
        }
        else {
            $results += [ordered]@{
                index = $job.Id
                ok = $false
                latencyMs = $null
                error = "Request timed out or returned no result."
            }
        }
    }

    Remove-Job -Job $jobs -Force

    $succeeded = @($results | Where-Object { $_.ok }).Count
    $failed = $Count - $succeeded
    $latencies = @($results | Where-Object { $_.ok -and $null -ne $_.latencyMs } | ForEach-Object { $_.latencyMs })

    return [pscustomobject][ordered]@{
        requested = $Count
        succeeded = $succeeded
        failed = $failed
        successRate = if ($Count -gt 0) { [Math]::Round($succeeded / $Count, 4) } else { 0 }
        averageLatencyMs = if ($latencies.Count -gt 0) { [Math]::Round(($latencies | Measure-Object -Average).Average, 2) } else { $null }
        maxLatencyMs = if ($latencies.Count -gt 0) { [Math]::Round(($latencies | Measure-Object -Maximum).Maximum, 2) } else { $null }
        results = $results
    }
}

Write-Host "Ollama server benchmark"
Write-Host "Endpoint: $Endpoint"
Write-Host "Model: $Model"
Write-Host "ConcurrentRequests: $ConcurrentRequests"
Write-Host ""

$installedModels = Assert-OllamaReady -ModelName $Model
$beforeHardware = Get-HardwareSnapshot
$beforeNvidia = Get-NvidiaSmiSnapshot

Write-Host "Running streaming latency benchmark..."
$streaming = Invoke-StreamingChatBenchmark -ModelName $Model -UserPrompt $Prompt

Write-Host "Running concurrency benchmark..."
$concurrency = Invoke-ConcurrencyBenchmark -ModelName $Model -Count $ConcurrentRequests

$afterHardware = Get-HardwareSnapshot
$afterNvidia = Get-NvidiaSmiSnapshot

$mode = "cpu"
if ($afterHardware.gpu -and $afterHardware.gpu.hasGpu) {
    $mode = "gpu-or-hybrid"
}

$report = [ordered]@{
    timestamp = (Get-Date).ToString("o")
    endpoint = $Endpoint
    model = $Model
    inferredMode = $mode
    installedModels = $installedModels
    basicMetrics = [ordered]@{
        firstTokenLatencyMs = $streaming.firstTokenLatencyMs
        tokensPerSecond = $streaming.tokensPerSecond
        ramBeforeGiB = if ($beforeHardware.memory) { $beforeHardware.memory.usedRamGiB } else { $null }
        ramAfterGiB = if ($afterHardware.memory) { $afterHardware.memory.usedRamGiB } else { $null }
        vramBeforeGiB = if ($beforeHardware.gpu) { $beforeHardware.gpu.dedicatedUsageGiB } else { $null }
        vramAfterGiB = if ($afterHardware.gpu) { $afterHardware.gpu.dedicatedUsageGiB } else { $null }
        concurrencySuccessRate = $concurrency.successRate
    }
    streaming = $streaming
    concurrency = $concurrency
    hardwareBefore = $beforeHardware
    hardwareAfter = $afterHardware
    nvidiaSmiBefore = $beforeNvidia
    nvidiaSmiAfter = $afterNvidia
    cpuOnlyGuidance = "GPU가 감지되지 않거나 VRAM 값을 읽을 수 없으면 CPU/RAM 기준으로 안정성을 봅니다. 이 경우 RAM 증가량, 첫 토큰 지연, tokens/sec, 동시 요청 실패율을 우선 지표로 삼습니다."
}

$report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $SaveJsonPath -Encoding UTF8

Write-Host ""
Write-Host "Benchmark summary"
Write-Host "- First token latency: $($report.basicMetrics.firstTokenLatencyMs) ms"
Write-Host "- Tokens/sec: $($report.basicMetrics.tokensPerSecond)"
Write-Host "- RAM used before/after: $($report.basicMetrics.ramBeforeGiB) / $($report.basicMetrics.ramAfterGiB) GiB"
Write-Host "- VRAM used before/after: $($report.basicMetrics.vramBeforeGiB) / $($report.basicMetrics.vramAfterGiB) GiB"
Write-Host "- Concurrency success rate: $($report.basicMetrics.concurrencySuccessRate)"
Write-Host "- Inferred mode: $mode"
Write-Host "- Report: $SaveJsonPath"
