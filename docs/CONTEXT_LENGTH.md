# Context Length

긴 대화나 RAG를 고려하면 컨텍스트 길이가 중요합니다. 너무 크게 잡으면 응답 속도와 메모리 사용량이 악화됩니다.

## 공식 기준

Ollama 공식 문서 기준 기본 컨텍스트는 VRAM에 따라 달라질 수 있습니다.

```text
< 24 GiB VRAM    -> 4K context
24-48 GiB VRAM   -> 32K context
>= 48 GiB VRAM   -> 256K context
```

`OLLAMA_CONTEXT_LENGTH` 환경변수 또는 `Modelfile`의 `PARAMETER num_ctx`로 조정할 수 있습니다.

## 실무 권장 시작값

```text
RAM 16GB / VRAM 6-8GB    -> num_ctx 4096
RAM 32GB / VRAM 12GB     -> num_ctx 8192
RAM 64GB / VRAM 16GB+    -> num_ctx 16384 이상 테스트
```

## 하드웨어 측정

현재 장비의 CPU/RAM/GPU/VRAM을 확인합니다.

```powershell
.\measure-hardware.ps1
```

JSON 출력:

```powershell
.\measure-hardware.ps1 -Json
```

실시간 모니터링:

```powershell
.\measure-hardware.ps1 -Watch -IntervalSeconds 5
```

측정 항목:

- CPU 이름, 아키텍처, 코어/스레드, 클럭, 현재 부하
- 총 RAM, 사용 RAM, 여유 RAM
- GPU 감지 여부, GPU 이름, 감지된 VRAM, GPU 사용률
- 권장 실행 모드: `gpu` 또는 `cpu`
- 권장 `num_ctx`

## 자동 적용

측정 결과에 따라 `.env`와 `Modelfile`을 자동 수정합니다.

```powershell
.\set-context-length.ps1 -Auto
```

적용되는 값:

```dotenv
OLLAMA_CONTEXT_LENGTH=...
```

```text
PARAMETER num_ctx ...
```

Ollama 서버를 이미 실행 중이었다면 완전히 종료한 뒤 다시 시작해야 합니다.

## GPU가 없는 경우

GPU가 없으면 CPU/RAM 기반으로 실행합니다.

- 작은 모델부터 사용합니다.
- `num_ctx`는 4096부터 시작합니다.
- RAM이 충분하면 8192, 16384를 순서대로 테스트합니다.
- `ollama ps`에서 `PROCESSOR`가 `100% CPU`인지 확인합니다.

CPU 모드는 동작 가능하지만 응답 속도가 크게 느려질 수 있습니다.
