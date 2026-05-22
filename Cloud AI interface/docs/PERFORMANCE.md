# Server Performance Verification

Ollama 서버 성능 검증의 기본 지표입니다.

1. 첫 토큰 대기 시간
2. 초당 토큰 수
3. RAM 사용량
4. VRAM 사용량
5. 동시 요청 처리 안정성

## 실행

```powershell
.\benchmark-server.ps1 -Model llama3.1 -ConcurrentRequests 3
```

결과는 기본적으로 다음 파일에 저장됩니다.

```text
benchmark-results.json
```

## GPU가 있는 경우

NVIDIA GPU가 있으면 `nvidia-smi`로 VRAM 사용량을 확인할 수 있습니다.

```powershell
nvidia-smi
```

모델이 GPU에 올라가면 VRAM 사용량이 증가합니다. `benchmark-server.ps1`은 `nvidia-smi`가 있으면 벤치마크 전후 상태를 함께 기록합니다.

Ollama는 모델이 단일 GPU VRAM에 들어가면 해당 GPU에 올리고, 들어가지 않으면 여러 GPU 또는 CPU/GPU 혼합으로 처리될 수 있습니다. 실제 배치는 `ollama ps`의 `PROCESSOR` 열로 확인합니다.

```powershell
ollama ps
```

## CPU만 있는 경우

GPU가 없거나 VRAM을 읽을 수 없는 환경도 정상 지원합니다. 이 경우에는 다음 지표를 우선 봅니다.

- 첫 토큰 대기 시간
- 초당 토큰 수
- RAM 증가량
- 동시 요청 실패율
- CPU 부하

CPU 모드는 동작 가능하지만 응답 속도가 느릴 수 있습니다. 작은 모델, 낮은 `num_ctx`, 낮은 동시 요청 수부터 검증합니다.

권장 시작점:

```powershell
.\set-context-length.ps1 -NumCtx 4096
.\benchmark-server.ps1 -Model llama3.1 -ConcurrentRequests 1
```

안정적이면 다음 단계로 올립니다.

```powershell
.\benchmark-server.ps1 -Model llama3.1 -ConcurrentRequests 2
.\set-context-length.ps1 -NumCtx 8192
```

## 결과 해석

- 첫 토큰 대기 시간이 길면 모델 로딩, 디스크, RAM/VRAM 부족, CPU 오프로딩을 의심합니다.
- 초당 토큰 수가 낮으면 CPU 모드이거나 모델이 너무 크거나 컨텍스트가 너무 큽니다.
- RAM 또는 VRAM이 계속 증가하면 동시 요청 수와 컨텍스트 길이를 줄입니다.
- 동시 요청 실패가 있으면 `OLLAMA_NUM_PARALLEL`, `OLLAMA_CONTEXT_LENGTH`, 모델 크기를 낮춰 테스트합니다.
