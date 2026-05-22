# Ollama Local Server 문서

이 폴더는 Ollama Local Server 관련 Markdown 문서를 한 곳에 모아둔 위치입니다.

명령은 기본적으로 상위 폴더에서 실행합니다.

```powershell
cd "runtime\ollama\server"
```

## 빠른 시작

- `install-ollama.ps1`: 전역 설치 없이 `cli` 폴더에 cli 설치
- `verify-runtime.ps1`: 서버 시작, API 테스트, 최종 검증을 한 번에 실행
- `00_FULL_GUIDE.md`: 2번부터 19번까지 전체 운영 절차
- `IMPLEMENTATION_ORDER.md`: 1번부터 16번까지 최종 구현 순서와 전체 검증 기준
- `ENVIRONMENT.md`: `.env`, 모델 저장 위치, 네트워크 바인딩
- `SECURITY.md`: 보안 프로파일, LAN/VPN/reverse proxy 기준
- `FIREWALL.md`: Windows 방화벽 설정
- `AUTO_START.md`: 작업 스케줄러 자동 시작

## 모델과 API

- `MODEL_GUIDE.md`: 운영용 모델 선택, 선택 삭제, RAG 최소 구성
- `CUSTOM_MODEL.md`: `Modelfile`, `local-assistant` 생성
- `CONTEXT_LENGTH.md`: CPU/RAM/GPU/VRAM 기반 `num_ctx` 설정
- `API_ENDPOINTS.md`: Ollama REST API 엔드포인트
- `HEALTHCHECK.md`: 서버 상태와 모델 존재 여부 확인
- `SK_CONNECTION.md`: Semantic Kernel 연결 기준

## 검증과 운영

- `PERFORMANCE.md`: 첫 토큰 지연, tokens/sec, RAM/VRAM, 동시 요청 측정
- `PORT_CONFLICT.md`: `11434` 포트 충돌 확인

## 실행 파일 위치

PowerShell 스크립트와 모델 목록 파일은 이 폴더의 상위 폴더에 있습니다.

```text
runtime/ollama/server
```
