# Ollama Local Server

Windows 로컬 PC에서 Ollama 서버를 설치하고, 모델을 내려받고, `http://localhost:11434` 상태를 확인하는 절차입니다.

이 문서의 PowerShell 명령은 기본적으로 상위 폴더에서 실행합니다.

```powershell
cd "runtime\ollama\server"
```

## 2. 설치

### Windows

```powershell
.\install-ollama.ps1
```

이 저장소는 전역 `winget` 설치 대신 공식 Windows ZIP을 `runtime\ollama\server\cli`에 설치합니다. `PATH` 등록을 하지 않으므로 삭제할 때 repo-local 폴더만 정리하면 됩니다.

설치 확인:

```powershell
.\cli\ollama.exe --version
```

서버 상태 확인:

```powershell
curl http://localhost:11434/api/tags
```

정상이라면 설치된 모델 목록 JSON이 나옵니다.

## 3. 모델 다운로드

초기 추천:

```powershell
ollama pull llama3.1
```

한국어/코딩 보조용 후보:

```powershell
ollama pull qwen2.5
ollama pull codellama
ollama pull mistral
```

모델 확인:

```powershell
ollama list
```

실행 테스트:

```powershell
ollama run llama3.1
```

## 전체 모델 다운로드

Ollama 공식 라이브러리에 현재 올라온 모든 모델 패밀리를 순서대로 다운로드하려면 다음을 실행합니다.

```powershell
.\pull-all-models.ps1
```

주의:

- 이 작업은 매우 오래 걸릴 수 있고 디스크를 많이 사용합니다.
- `cloud`로만 제공되는 모델이나 권한/라이선스/플랫폼 제한이 있는 모델은 `ollama pull`이 실패할 수 있습니다.
- 실패한 모델은 `pull-results.json`에 기록되고, 스크립트는 다음 모델로 계속 진행합니다.

기본 추천 모델만 받으려면:

```powershell
.\pull-models.ps1 -ModelFile .\models.recommended.txt
```

한국어/코딩 후보만 받으려면:

```powershell
.\pull-models.ps1 -ModelFile .\models.korean-coding.txt
```

설치 없이 현재 상태만 점검하려면:

```powershell
.\check-server.ps1
```

## 4. 서버 직접 실행

일반적으로 Ollama 앱이 백그라운드 서버를 자동 실행합니다.

수동 실행은 다음과 같습니다.

```powershell
ollama serve
```

이 폴더의 실행 스크립트를 쓰려면:

```powershell
.\start-server.ps1
```

이미 실행 중인지 확인하고, 실행 중이 아니면 `ollama serve`를 시작합니다. 별도 백그라운드 프로세스로 실행하려면:

```powershell
.\start-server.ps1 -Background
```

기본 API 주소:

```text
http://localhost:11434
```

Ollama REST API의 주요 엔드포인트:

```text
GET  /api/tags
POST /api/chat
POST /api/generate
POST /api/embed
POST /api/embeddings
```

`/api/chat`은 대화형 응답용이고, 기본적으로 스트리밍 응답을 반환합니다. `"stream": false`를 넣으면 단일 JSON 응답으로 받을 수 있습니다.

API 동작을 한 번에 확인하려면:

```powershell
.\test-api.ps1 -Model llama3.1
```

## 5. API 동작 검증

### 5-1. 모델 목록 확인

```powershell
curl http://localhost:11434/api/tags
```

### 5-2. 채팅 호출 테스트

```powershell
curl http://localhost:11434/api/chat `
  -H "Content-Type: application/json" `
  -d '{
    "model": "llama3.1",
    "messages": [
      { "role": "system", "content": "너는 한국어로 답하는 로컬 AI 비서다." },
      { "role": "user", "content": "Ollama가 뭔지 짧게 설명해줘." }
    ],
    "stream": false
  }'
```

스크립트 검증:

```powershell
.\test-api.ps1 -Model llama3.1
```

## 6. OpenAI 호환 API 확인

Semantic Kernel이나 다른 OpenAI 호환 클라이언트와 붙일 때는 이 경로를 쓸 수 있습니다.

```text
http://localhost:11434/v1/chat/completions
```

테스트:

```powershell
curl http://localhost:11434/v1/chat/completions `
  -H "Content-Type: application/json" `
  -d '{
    "model": "llama3.1",
    "messages": [
      { "role": "user", "content": "안녕. 한 문장으로 답해줘." }
    ]
  }'
```

Ollama는 OpenAI Chat Completions API 일부와 호환됩니다. Chat completions, streaming, JSON mode 등을 지원합니다.

## 7. Semantic Kernel 연결 기준

Semantic Kernel에서는 보통 다음 주소를 기준으로 연결합니다.

```text
endpoint: http://localhost:11434
modelId: llama3.1
```

예시:

```csharp
builder.AddOllamaChatCompletion(
    modelId: "llama3.1",
    endpoint: new Uri("http://localhost:11434")
);
```

즉, Ollama 쪽 구현 목표는 다음입니다.

1. Ollama 서버가 항상 켜져 있어야 함
2. `11434` 포트가 정상 응답해야 함
3. 지정한 `modelId`가 `ollama list`에 존재해야 함
4. `/api/chat` 또는 `/v1/chat/completions`가 정상 작동해야 함

자세한 연결 기준은 `SK_CONNECTION.md`에 정리했습니다.

## 8. 모델 저장 위치 변경

Windows 기본 저장 위치:

```text
C:\Users\사용자명\.ollama\models
```

이 저장소에서는 모델 저장 위치를 다음 폴더로 지정합니다.

```text
runtime/ollama/server/models
```

루트 `.env` 설정:

```dotenv
OLLAMA_MODELS=runtime\ollama\server\models
```

설정 후 Ollama를 완전히 종료하고 다시 실행해야 합니다. 이 폴더의 `start-server.ps1`은 루트 `.env`를 읽고, 상대경로를 repo 루트 기준 절대경로로 변환해서 `ollama serve` 프로세스에 환경변수를 적용합니다.

## 9. 네트워크 접근 허용

다른 PC, Unity 클라이언트, NAS 내부 서비스에서 접근하려면 바인딩 주소를 바꿔야 합니다.

기본:

```text
127.0.0.1:11434
```

LAN 허용:

```text
0.0.0.0:11434
```

루트 `.env` 설정:

```dotenv
OLLAMA_HOST=0.0.0.0:11434
```

그 후 접속 주소는 다음처럼 바뀝니다.

```text
http://서버PC_IP:11434
```

예:

```text
http://192.168.0.25:11434
```

주의: Ollama 자체에는 일반적인 웹서비스 수준의 인증 계층이 없습니다. 외부 인터넷에 직접 노출하면 안 됩니다. LAN 내부 또는 VPN 내부에서만 열어야 합니다.

## 10. Windows 방화벽 설정

다른 PC에서 접근할 경우 `11434` 포트를 허용합니다.

관리자 PowerShell:

```powershell
New-NetFirewallRule `
  -DisplayName "Ollama Local Server 11434" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 11434 `
  -Action Allow
```

이 폴더의 스크립트를 사용하려면 관리자 PowerShell에서 실행합니다.

```powershell
.\enable-firewall-rule.ps1
```

확인:

```powershell
Test-NetConnection 192.168.0.25 -Port 11434
```

스크립트로 확인하려면:

```powershell
.\test-network-access.ps1 -ServerIp 192.168.0.25
```

기본 스크립트는 LAN 내부 접근만 허용하도록 `LocalSubnet`으로 제한합니다. 외부 인터넷에는 직접 노출하지 않습니다.

자세한 내용은 `FIREWALL.md`에 정리했습니다.

## 11. 커스텀 모델 설정

Ollama는 `Modelfile`로 모델별 실행 조건을 만들 수 있습니다.

예:

```text
FROM llama3.1

PARAMETER temperature 0.3
PARAMETER num_ctx 4096

SYSTEM """
너는 한국어로 답하는 로컬 NAS/서버/개발 보조 AI다.
답변은 실무 절차 중심으로 작성한다.
"""
```

생성:

```powershell
ollama create local-assistant -f Modelfile
```

실행:

```powershell
ollama run local-assistant
```

이 폴더의 스크립트를 사용하려면:

```powershell
.\create-custom-model.ps1
```

이후 Semantic Kernel에서는 다음처럼 사용하면 됩니다.

```text
modelId: "local-assistant"
```

`num_ctx`는 컨텍스트 창 크기를 설정하는 파라미터입니다. Ollama `Modelfile`에서 `PARAMETER num_ctx 4096` 형식으로 설정할 수 있습니다.

자세한 내용은 `CUSTOM_MODEL.md`에 정리했습니다.

## 12. 컨텍스트 길이 설정

긴 대화나 RAG를 고려하면 컨텍스트 길이가 중요합니다. Ollama 공식 문서 기준 기본 컨텍스트는 VRAM에 따라 달라질 수 있습니다.

```text
< 24 GiB VRAM    -> 4K context
24-48 GiB VRAM   -> 32K context
>= 48 GiB VRAM   -> 256K context
```

실무 권장 시작값:

```text
RAM 16GB / VRAM 6-8GB    -> num_ctx 4096
RAM 32GB / VRAM 12GB     -> num_ctx 8192
RAM 64GB / VRAM 16GB+    -> num_ctx 16384 이상 테스트
```

너무 크게 잡으면 응답 속도와 메모리 사용량이 악화됩니다.

현재 장비의 CPU/RAM/GPU/VRAM을 측정하고 권장값을 보려면:

```powershell
.\measure-hardware.ps1
```

실시간 모니터링:

```powershell
.\measure-hardware.ps1 -Watch -IntervalSeconds 5
```

GPU가 없으면 CPU/RAM 기준으로 보수적인 컨텍스트를 추천합니다. 자동 추천값을 `.env`의 `OLLAMA_CONTEXT_LENGTH`와 `Modelfile`의 `PARAMETER num_ctx`에 반영하려면:

```powershell
.\set-context-length.ps1 -Auto
```

수동으로 지정하려면:

```powershell
.\set-context-length.ps1 -NumCtx 8192
```

커스텀 모델 생성 시 자동 측정값을 먼저 적용하려면:

```powershell
.\create-custom-model.ps1 -AutoContext
```

자세한 내용은 `CONTEXT_LENGTH.md`에 정리했습니다.

## 13. 서버 성능 검증

기본 지표:

1. 첫 토큰 대기 시간
2. 초당 토큰 수
3. RAM 사용량
4. VRAM 사용량
5. 동시 요청 처리 안정성

Windows에서는 작업 관리자 또는 NVIDIA GPU 사용량으로 확인합니다.

```powershell
nvidia-smi
```

모델이 GPU에 올라가면 VRAM 사용량이 증가합니다.

Ollama는 모델이 단일 GPU VRAM에 들어가면 해당 GPU에 올리고, 들어가지 않으면 여러 GPU 또는 CPU/GPU 혼합으로 처리될 수 있습니다. 실제 배치는 다음 명령으로 확인합니다.

```powershell
ollama ps
```

이 폴더의 벤치마크 스크립트:

```powershell
.\benchmark-server.ps1 -Model llama3.1 -ConcurrentRequests 3
```

GPU가 없으면 CPU/RAM 기준으로 성능을 측정합니다. 이 경우 VRAM 지표는 `null` 또는 `0`으로 남고, 첫 토큰 지연/초당 토큰 수/RAM 증가량/동시 요청 성공률을 우선 봅니다.

자세한 내용은 `PERFORMANCE.md`에 정리했습니다.

## 14. 운영용 권장 모델 구성

일반 대화:

```text
llama3.1
qwen2.5
gemma2
mistral
```

코딩 보조:

```text
codellama
qwen2.5-coder
deepseek-coder
```

임베딩/RAG:

```text
nomic-embed-text
mxbai-embed-large
```

RAG 최소 구성:

```text
Chat Model      : qwen2.5 또는 llama3.1
Embedding Model : nomic-embed-text
Vector DB       : SQLite / Qdrant / Chroma / PostgreSQL pgvector
```

모델은 자동으로 전부 설치하지 않고, 사용자가 직접 고른 목록만 `models.selected.txt`에 저장합니다.

```powershell
.\select-models.ps1 -Select qwen2.5,nomic-embed-text
.\pull-models.ps1 -ModelFile .\models.selected.txt
```

한글 별칭:

```powershell
.\select-models.ps1 -선택 qwen2.5,nomic-embed-text
```

한글 이름의 실행 파일:

```powershell
.\select-shortcut.ps1 qwen2.5,nomic-embed-text
```

선택 삭제:

```powershell
.\select-models.ps1 -Remove qwen2.5
```

한글 별칭:

```powershell
.\select-models.ps1 -선택삭제 qwen2.5
```

한글 이름의 실행 파일:

```powershell
.\unselect-shortcut.ps1 qwen2.5
```

RAG 최소 구성만 선택하려면:

```powershell
.\select-models.ps1 -RagMinimal
```

현재 선택 목록 확인:

```powershell
.\select-models.ps1 -List
```

자세한 내용은 `MODEL_GUIDE.md`에 정리했습니다.

## 15. 서버 헬스체크 구현

Semantic Kernel 앱 시작 전에 Ollama 서버 상태를 먼저 확인합니다.

```csharp
public static async Task<bool> CheckOllamaAsync()
{
    using var http = new HttpClient();

    try
    {
        var response = await http.GetAsync("http://localhost:11434/api/tags");
        return response.IsSuccessStatusCode;
    }
    catch
    {
        return false;
    }
}
```

콘솔 앱은 서버가 없으면 다음 메시지를 출력하고 종료합니다.

```text
Ollama 서버가 실행 중이 아닙니다.
```

## 16. 모델 존재 여부 확인

실무에서는 JSON 파싱을 사용합니다. 현재 Connector는 `/api/tags` 응답의 `models[].name`만 파싱해서 `modelName` 또는 `modelName:tag`와 비교합니다.

```text
IOllamaConnector.HasModelAsync(...)
IOllamaConnector.CheckHealthAsync(...)
SemanticKernelOllamaConnector.GetInstalledModelsAsync(...)
```

API 헬스체크는 상태를 구분합니다.

```text
ok
model-missing
ollama-unreachable
```

자세한 내용은 `HEALTHCHECK.md`에 정리했습니다.

## 17. 자동 시작 구성 작업 스케줄러

작업 스케줄러에서 로그인 시 실행:

```powershell
ollama serve
```

권장 조건:

```text
트리거: 사용자 로그인 시
동작: ollama serve
권한: 가장 높은 권한으로 실행
```

단, 이미 Ollama 앱이 서버를 띄우고 있으면 포트 충돌이 날 수 있습니다. 이 저장소에서는 `ollama serve`를 직접 등록하지 않고 `start-server.ps1`를 등록합니다. 작업 스케줄러에서는 foreground로 실행되어야 서버 프로세스가 계속 유지됩니다.

등록:

```powershell
.\register-startup-task.ps1 -RunLevelHighest
```

확인:

```powershell
.\get-startup-task.ps1
```

삭제:

```powershell
.\unregister-startup-task.ps1
```

자세한 내용은 `AUTO_START.md`에 정리했습니다.

## 18. 포트 충돌 확인

```powershell
netstat -ano | findstr :11434
```

프로세스 확인:

```powershell
tasklist /FI "PID eq 프로세스ID"
```

이미 사용 중이면 기존 Ollama가 떠 있는 것입니다.

스크립트:

```powershell
.\check-port-conflict.ps1
```

자세한 내용은 `PORT_CONFLICT.md`에 정리했습니다.

## 19. 보안 구성

권장 보안 수준:

```text
개인 PC 단독 사용      -> localhost 유지
집/사무실 LAN 사용     -> 0.0.0.0 허용 + Windows 방화벽으로 내부 IP만 허용
외부 접속 필요         -> 직접 포트포워딩 금지, VPN/Tailscale/WireGuard 사용
공개 서버 운영         -> Nginx Reverse Proxy + 인증 + HTTPS 필요
```

Ollama를 인터넷에 직접 노출하는 구성은 권장하지 않습니다.

현재 `.env`는 localhost 사용 기준입니다. LAN 공개가 필요할 때만 관리자 PowerShell에서 방화벽 규칙을 만든 뒤 전환합니다.

```dotenv
OLLAMA_SECURITY_PROFILE=localhost
OLLAMA_HOST=127.0.0.1:11434
OLLAMA_ALLOWED_REMOTE_ADDRESSES=
```

보안 프로파일 변경:

```powershell
.\set-security-profile.ps1 -Profile localhost
.\set-security-profile.ps1 -Profile lan
.\set-security-profile.ps1 -Profile vpn -AllowedRemoteAddresses 100.64.0.0/10
.\set-security-profile.ps1 -Profile reverse-proxy
```

보안 감사:

```powershell
.\audit-security.ps1
```

자세한 내용은 `SECURITY.md`에 정리했습니다.

## 기본 엔드포인트

- Ollama API: `http://localhost:11434`
- 모델 목록: `http://localhost:11434/api/tags`
- OpenAI 호환 엔드포인트: `http://localhost:11434/v1`

`runtime/semantic-kernel/LocalAI.Api/appsettings.json`의 `Endpoint` 값과 이 주소가 같아야 합니다.
