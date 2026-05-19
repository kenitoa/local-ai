param(
    [switch]$Json,
    [switch]$Watch,
    [int]$IntervalSeconds = 5,
    [string]$SaveJsonPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Convert-BytesToGiB {
    param([double]$Bytes)
    if ($Bytes -le 0) {
        return 0
    }

    return [Math]::Round($Bytes / 1GB, 2)
}

function Convert-KiBToGiB {
    param([double]$KiB)
    if ($KiB -le 0) {
        return 0
    }

    return [Math]::Round(($KiB * 1024) / 1GB, 2)
}

function Get-ArchitectureName {
    param([int]$Architecture)

    switch ($Architecture) {
        0 { "x86" }
        1 { "MIPS" }
        2 { "Alpha" }
        3 { "PowerPC" }
        5 { "ARM" }
        6 { "Itanium" }
        9 { "x64" }
        12 { "ARM64" }
        default { "Unknown($Architecture)" }
    }
}

function Get-GpuMemoryCounters {
    $usageBytes = $null
    $limitBytes = $null

    try {
        $counters = Get-Counter -Counter "\GPU Adapter Memory(*)\Dedicated Usage", "\GPU Adapter Memory(*)\Dedicated Limit" -ErrorAction Stop
        $usageBytes = ($counters.CounterSamples | Where-Object { $_.Path -like "*dedicated usage" } | Measure-Object -Property CookedValue -Sum).Sum
        $limitBytes = ($counters.CounterSamples | Where-Object { $_.Path -like "*dedicated limit" } | Measure-Object -Property CookedValue -Sum).Sum
    }
    catch {
        return [ordered]@{
            dedicatedUsageGiB = $null
            dedicatedLimitGiB = $null
        }
    }

    return [ordered]@{
        dedicatedUsageGiB = if ($null -ne $usageBytes) { Convert-BytesToGiB $usageBytes } else { $null }
        dedicatedLimitGiB = if ($null -ne $limitBytes) { Convert-BytesToGiB $limitBytes } else { $null }
    }
}

function Get-GpuUtilizationPercent {
    try {
        $samples = Get-Counter -Counter "\GPU Engine(*)\Utilization Percentage" -ErrorAction Stop
        $sum = ($samples.CounterSamples | Measure-Object -Property CookedValue -Sum).Sum
        if ($null -eq $sum) {
            return $null
        }

        return [Math]::Round([Math]::Min($sum, 100), 1)
    }
    catch {
        return $null
    }
}

function Get-SafeCimInstance {
    param([string]$ClassName)

    try {
        return @(Get-CimInstance $ClassName -ErrorAction Stop)
    }
    catch {
        return @()
    }
}

function Get-FallbackTotalRamGiB {
    try {
        Add-Type -AssemblyName Microsoft.VisualBasic -ErrorAction Stop
        $computerInfo = [Microsoft.VisualBasic.Devices.ComputerInfo]::new()
        return Convert-BytesToGiB ([double]$computerInfo.TotalPhysicalMemory)
    }
    catch {
        return 0
    }
}

function Get-FallbackFreeRamGiB {
    try {
        Add-Type -AssemblyName Microsoft.VisualBasic -ErrorAction Stop
        $computerInfo = [Microsoft.VisualBasic.Devices.ComputerInfo]::new()
        return Convert-BytesToGiB ([double]$computerInfo.AvailablePhysicalMemory)
    }
    catch {
        return 0
    }
}

function Get-HardwareSnapshot {
    $computer = @(Get-SafeCimInstance Win32_ComputerSystem)
    $os = @(Get-SafeCimInstance Win32_OperatingSystem)
    $processors = @(Get-SafeCimInstance Win32_Processor)
    $videoControllers = @(Get-SafeCimInstance Win32_VideoController)

    $totalRamGiB = 0
    if ($computer.Count -gt 0 -and $computer[0].TotalPhysicalMemory) {
        $totalRamGiB = Convert-BytesToGiB ([double]$computer[0].TotalPhysicalMemory)
    }
    if ($totalRamGiB -le 0) {
        $totalRamGiB = Get-FallbackTotalRamGiB
    }

    $freeRamGiB = 0
    if ($os.Count -gt 0 -and $os[0].FreePhysicalMemory) {
        $freeRamGiB = Convert-KiBToGiB ([double]$os[0].FreePhysicalMemory)
    }
    if ($freeRamGiB -le 0) {
        $freeRamGiB = Get-FallbackFreeRamGiB
    }

    $usedRamGiB = [Math]::Round([Math]::Max($totalRamGiB - $freeRamGiB, 0), 2)

    $processor = if ($processors.Count -gt 0) { $processors[0] } else { $null }
    $coreMeasure = $processors | Measure-Object -Property NumberOfCores -Sum
    $logicalMeasure = $processors | Measure-Object -Property NumberOfLogicalProcessors -Sum
    $totalCores = if ($coreMeasure.PSObject.Properties.Match("Sum").Count -gt 0 -and $null -ne $coreMeasure.Sum) { $coreMeasure.Sum } else { 0 }
    $totalLogicalProcessors = if ($logicalMeasure.PSObject.Properties.Match("Sum").Count -gt 0 -and $null -ne $logicalMeasure.Sum) { $logicalMeasure.Sum } else { 0 }
    if (-not $totalCores) {
        $totalCores = [Environment]::ProcessorCount
    }
    if (-not $totalLogicalProcessors) {
        $totalLogicalProcessors = [Environment]::ProcessorCount
    }

    $loadMeasure = $processors | Measure-Object -Property LoadPercentage -Average
    $averageCpuLoad = if ($loadMeasure.PSObject.Properties.Match("Average").Count -gt 0 -and $null -ne $loadMeasure.Average) { $loadMeasure.Average } else { $null }
    if ($null -ne $averageCpuLoad) {
        $averageCpuLoad = [Math]::Round($averageCpuLoad, 1)
    }

    $gpuMemoryCounters = Get-GpuMemoryCounters
    $gpuUtilization = Get-GpuUtilizationPercent

    $gpus = @()
    foreach ($gpu in $videoControllers) {
        $adapterRamGiB = $null
        if ($null -ne $gpu.AdapterRAM -and [double]$gpu.AdapterRAM -gt 0) {
            $adapterRamGiB = Convert-BytesToGiB ([double]$gpu.AdapterRAM)
        }

        $isMicrosoftBasic = $gpu.Name -match "Microsoft Basic|Remote Display|RDP"
        $isLikelyAccelerator = $gpu.Name -match "NVIDIA|GeForce|RTX|GTX|Quadro|Tesla|AMD|Radeon|Intel\(R\) Arc|Intel Arc"

        $gpus += [ordered]@{
            name = $gpu.Name
            videoProcessor = $gpu.VideoProcessor
            driverVersion = $gpu.DriverVersion
            status = $gpu.Status
            adapterRamGiB = $adapterRamGiB
            isLikelyAccelerator = [bool]($isLikelyAccelerator -and -not $isMicrosoftBasic)
        }
    }

    $usableGpus = @($gpus | Where-Object { $_.isLikelyAccelerator })
    $maxDetectedVramGiB = 0
    foreach ($gpu in $usableGpus) {
        if ($null -ne $gpu.adapterRamGiB -and $gpu.adapterRamGiB -gt $maxDetectedVramGiB) {
            $maxDetectedVramGiB = $gpu.adapterRamGiB
        }
    }

    if ($gpuMemoryCounters.dedicatedLimitGiB -and $gpuMemoryCounters.dedicatedLimitGiB -gt $maxDetectedVramGiB) {
        $maxDetectedVramGiB = $gpuMemoryCounters.dedicatedLimitGiB
    }

    $hasGpu = $usableGpus.Count -gt 0
    $recommendation = Get-ContextRecommendation -HasGpu:$hasGpu -RamGiB $totalRamGiB -VramGiB $maxDetectedVramGiB

    return [ordered]@{
        timestamp = (Get-Date).ToString("o")
        cpu = [ordered]@{
            name = if ($processor) { $processor.Name } else { "Unknown CPU" }
            manufacturer = if ($processor) { $processor.Manufacturer } else { "Unknown" }
            architecture = if ($processor) { Get-ArchitectureName ([int]$processor.Architecture) } else { [System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString() }
            physicalCores = [int]$totalCores
            logicalProcessors = [int]$totalLogicalProcessors
            maxClockMHz = if ($processor -and $processor.MaxClockSpeed) { [int]$processor.MaxClockSpeed } else { $null }
            currentLoadPercent = $averageCpuLoad
        }
        memory = [ordered]@{
            totalRamGiB = $totalRamGiB
            usedRamGiB = $usedRamGiB
            freeRamGiB = $freeRamGiB
        }
        gpu = [ordered]@{
            hasGpu = $hasGpu
            maxDetectedVramGiB = [Math]::Round($maxDetectedVramGiB, 2)
            currentUtilizationPercent = $gpuUtilization
            dedicatedUsageGiB = $gpuMemoryCounters.dedicatedUsageGiB
            dedicatedLimitGiB = $gpuMemoryCounters.dedicatedLimitGiB
            devices = $gpus
        }
        recommendation = $recommendation
    }
}

function Get-ContextRecommendation {
    param(
        [bool]$HasGpu,
        [double]$RamGiB,
        [double]$VramGiB
    )

    $mode = "cpu"
    $numCtx = 4096
    $reason = "GPU 가속 장치를 확인하지 못했습니다. CPU/RAM 기준으로 보수적으로 설정합니다."

    if ($HasGpu -and $VramGiB -gt 0) {
        $mode = "gpu"

        if ($VramGiB -lt 10) {
            $numCtx = 4096
            $reason = "VRAM 10GiB 미만 장비는 메모리와 응답 속도를 위해 4K를 권장합니다."
        }
        elseif ($VramGiB -lt 16) {
            $numCtx = 8192
            $reason = "VRAM 10-16GiB 장비는 8K부터 시작하는 것이 안정적입니다."
        }
        elseif ($VramGiB -lt 24) {
            $numCtx = 16384
            $reason = "VRAM 16-24GiB 장비는 16K를 먼저 테스트합니다."
        }
        elseif ($VramGiB -lt 48) {
            $numCtx = 32768
            $reason = "Ollama 공식 기본값 기준 24-48GiB VRAM 구간은 32K 컨텍스트입니다."
        }
        else {
            $numCtx = 65536
            $reason = "48GiB 이상 VRAM은 큰 컨텍스트를 사용할 수 있지만 로컬 실무 기본값은 64K부터 검증합니다."
        }
    }
    else {
        if ($RamGiB -lt 24) {
            $numCtx = 4096
            $reason = "RAM 24GiB 미만 CPU 모드는 4K를 권장합니다."
        }
        elseif ($RamGiB -lt 48) {
            $numCtx = 8192
            $reason = "RAM 24-48GiB CPU 모드는 8K부터 테스트합니다."
        }
        else {
            $numCtx = 16384
            $reason = "RAM 48GiB 이상 CPU 모드는 16K까지 테스트할 수 있으나 속도 저하를 확인해야 합니다."
        }
    }

    return [ordered]@{
        inferenceMode = $mode
        numCtx = $numCtx
        ollamaContextLength = $numCtx
        reason = $reason
        cpuFallback = -not $HasGpu
        guidance = if ($HasGpu) {
            "모델이 VRAM에 전부 올라가지 않으면 CPU 오프로딩으로 느려질 수 있습니다. ollama ps의 PROCESSOR 열을 확인하세요."
        }
        else {
            "GPU가 없으면 CPU/RAM 기반으로 실행합니다. 작은 모델과 4K-8K 컨텍스트부터 시작하세요."
        }
    }
}

function Write-HardwareReport {
    param([object]$Snapshot)

    Clear-Host
    Write-Host "Ollama hardware monitor"
    Write-Host "Time: $($Snapshot.timestamp)"
    Write-Host ""
    Write-Host "CPU"
    Write-Host "- Name: $($Snapshot.cpu.name)"
    Write-Host "- Architecture: $($Snapshot.cpu.architecture)"
    Write-Host "- Cores/Threads: $($Snapshot.cpu.physicalCores)/$($Snapshot.cpu.logicalProcessors)"
    Write-Host "- Max clock: $($Snapshot.cpu.maxClockMHz) MHz"
    Write-Host "- Load: $($Snapshot.cpu.currentLoadPercent)%"
    Write-Host ""
    Write-Host "RAM"
    Write-Host "- Total: $($Snapshot.memory.totalRamGiB) GiB"
    Write-Host "- Used: $($Snapshot.memory.usedRamGiB) GiB"
    Write-Host "- Free: $($Snapshot.memory.freeRamGiB) GiB"
    Write-Host ""
    Write-Host "GPU"
    Write-Host "- GPU detected: $($Snapshot.gpu.hasGpu)"
    Write-Host "- Max detected VRAM: $($Snapshot.gpu.maxDetectedVramGiB) GiB"
    Write-Host "- GPU utilization: $($Snapshot.gpu.currentUtilizationPercent)%"
    Write-Host "- Dedicated memory usage/limit: $($Snapshot.gpu.dedicatedUsageGiB) / $($Snapshot.gpu.dedicatedLimitGiB) GiB"
    foreach ($gpu in $Snapshot.gpu.devices) {
        Write-Host "  - $($gpu.name), adapterRam=$($gpu.adapterRamGiB) GiB, accelerator=$($gpu.isLikelyAccelerator)"
    }
    Write-Host ""
    Write-Host "Recommendation"
    Write-Host "- Mode: $($Snapshot.recommendation.inferenceMode)"
    Write-Host "- num_ctx: $($Snapshot.recommendation.numCtx)"
    Write-Host "- OLLAMA_CONTEXT_LENGTH: $($Snapshot.recommendation.ollamaContextLength)"
    Write-Host "- Reason: $($Snapshot.recommendation.reason)"
    Write-Host "- Guidance: $($Snapshot.recommendation.guidance)"
}

do {
    $snapshot = Get-HardwareSnapshot

    if ($SaveJsonPath) {
        $snapshot | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $SaveJsonPath -Encoding UTF8
    }

    if ($Json) {
        $snapshot | ConvertTo-Json -Depth 8
    }
    else {
        Write-HardwareReport -Snapshot $snapshot
    }

    if ($Watch) {
        Start-Sleep -Seconds $IntervalSeconds
    }
} while ($Watch)
