# Final Implementation Order

이 문서는 Ollama Local Server와 Semantic Kernel 연결을 끝까지 막힘 없이 확인하기 위한 최종 순서입니다.

명령은 기본적으로 상위 폴더에서 실행합니다.

```powershell
cd "runtime\ollama\server"
```

## 순서

1. Ollama repo-local CLI 설치
2. `.\cli\ollama.exe --version` 확인
3. `ollama pull llama3.1`
4. `ollama run llama3.1` 테스트
5. `http://localhost:11434/api/tags` 확인
6. `/api/chat` 호출 테스트
7. Semantic Kernel에서 endpoint 연결
8. 모델 저장 위치 `OLLAMA_MODELS` 설정
9. 필요 시 `OLLAMA_HOST=0.0.0.0:11434` 설정
10. Windows 방화벽 `11434` 허용
11. `Modelfile`로 `local-assistant` 모델 생성
12. Semantic Kernel `modelId`를 `local-assistant`로 변경
13. 헬스체크 코드 추가
14. 모델 존재 여부 체크 추가
15. 자동 시작 구성
16. 성능 측정 및 `num_ctx` 조정

## 현재 구현 매핑

| 순서 | 구현 파일 |
| --- | --- |
| 1-2 | `install-ollama.ps1`, `check-server.ps1` |
| 3-4 | `pull-models.ps1`, `models.selected.txt` |
| 5-6 | `test-api.ps1`, `API_ENDPOINTS.md` |
| 7 | `runtime/semantic-kernel/LocalAI.Api/appsettings.json`, `SK_CONNECTION.md` |
| 8-9 | `.env`, `ENVIRONMENT.md`, `start-server.ps1` |
| 10 | `enable-firewall-rule.ps1`, `FIREWALL.md` |
| 11 | `Modelfile`, `create-custom-model.ps1`, `CUSTOM_MODEL.md` |
| 12 | `runtime/semantic-kernel/LocalAI.Api/appsettings.json` |
| 13-14 | `IOllamaConnector`, `SemanticKernelOllamaConnector`, `HEALTHCHECK.md` |
| 15 | `register-startup-task.ps1`, `AUTO_START.md` |
| 16 | `measure-hardware.ps1`, `set-context-length.ps1`, `benchmark-server.ps1`, `CONTEXT_LENGTH.md`, `PERFORMANCE.md` |

## 최종 검증

전체 흐름 검증:

```powershell
.\validate-final-implementation.ps1
```

서버 시작, API 테스트, 최종 검증을 한 번에 실행:

```powershell
.\verify-runtime.ps1
```

선택 모델 다운로드와 커스텀 모델 생성까지 포함:

```powershell
.\verify-runtime.ps1 -PullSelectedModels -CreateCustomModel
```

빌드를 생략하고 설정만 확인:

```powershell
.\validate-final-implementation.ps1 -SkipBuild
```

경고도 실패로 보고 싶으면:

```powershell
.\validate-final-implementation.ps1 -Strict
```

검증 리포트:

```text
final-validation-report.json
```

## 정상 완료 기준

- repo-local `cli\ollama.exe --version`이 동작합니다.
- `/api/tags`가 응답합니다.
- `local-assistant`가 설치되어 있습니다.
- `/api/chat`이 `local-assistant`로 응답합니다.
- Semantic Kernel 설정의 endpoint는 `http://localhost:11434`입니다.
- Semantic Kernel 설정의 modelId는 `local-assistant`입니다.
- `OLLAMA_MODELS` 경로가 실제 폴더를 가리킵니다.
- LAN 공개 구성에서는 Windows 방화벽이 내부 IP만 허용합니다.
- 작업 스케줄러가 필요하면 `Ollama Local Server` 작업이 등록되어 있습니다.
- 성능 측정 스크립트가 실행 가능하고 `OLLAMA_CONTEXT_LENGTH`가 설정되어 있습니다.

## 아직 설치 전이면 정상적으로 남는 항목

아래 항목은 Ollama 설치/모델 생성 전에는 실패 또는 경고가 날 수 있습니다.

- cli 없음
- `/api/tags` 미응답
- `local-assistant` 미설치
- LAN 공개 모드에서 Windows 방화벽 규칙 없음
- 작업 스케줄러 미등록

이 경우 순서대로 `install-ollama.ps1`, `start-server.ps1`, `create-custom-model.ps1`, `enable-firewall-rule.ps1`, `register-startup-task.ps1`을 진행합니다.
