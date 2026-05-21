# Local AI

`local-ai`는 Windows PC 안에서 실행되는 로컬 AI 데스크톱 소프트웨어입니다. 사용자는 복잡한 모델 경로, Ollama 명령, .NET 런타임 구조를 몰라도 `publish/start-local-ai.cmd`를 실행해서 채팅, 모델 선택, AI 마켓, 설정, 로그 기능을 사용할 수 있습니다.

이 프로젝트의 핵심 목표는 하나입니다.

> 외부 사용자는 하나의 `Cloud AI Interface`만 호출하고, 내부에서는 여러 AI expert를 선택, 실행, 조합, 검증해서 최종 응답을 만든다.

## 빠른 실행

배포용 실행 파일은 `publish` 폴더에 있습니다.

```powershell
publish\start-local-ai.cmd
```

실행하면 다음 순서로 동작합니다.

1. 로컬 Ollama 서버를 준비합니다.
2. ASP.NET API 서버를 `http://localhost:5088`에서 실행합니다.
3. 필수 API가 준비됐는지 확인합니다.
4. Windows 데스크톱 앱을 실행합니다.
5. 데스크톱 앱 안에서 `apps/web/index.html` 기반 UI를 그대로 표시합니다.

브라우저가 아니라 Windows desktop app으로 열리는 것이 기본 동작입니다.

## 이 소프트웨어가 하는 일

`local-ai`는 로컬 AI 모델을 쉽게 쓰기 위한 통합 인터페이스입니다.

주요 기능은 다음과 같습니다.

- 로컬 AI 채팅
- Ollama 모델 실행
- .NET/ONNX 기반 모델 등록 준비
- 여러 모델을 조합하는 Composition Profile
- AI 마켓에서 모델 다운로드/삭제
- Cloud AI Interface 기반 expert orchestration
- 프로젝트/채팅 세션 관리
- 실행 로그와 WebView 오류 로그 확인

즉, 단순히 모델 하나를 호출하는 앱이 아니라 여러 모델과 런타임을 하나의 시스템처럼 묶는 로컬 AI 런타임입니다.

## 전체 구조

```text
사용자
  ↓
Windows Desktop App
  ↓
Web UI index.html
  ↓
ASP.NET API :5088
  ↓
Cloud AI Interface
  ↓
Router / Executor / Aggregator / Judge
  ↓
Ollama Expert / .NET Expert / ONNX Expert / External API Expert
```

사용자는 데스크톱 앱을 사용하지만, 실제 화면은 웹 UI입니다. WPF 데스크톱 앱은 WebView2를 사용해서 `apps/web/index.html`을 그대로 띄웁니다. 그래서 웹과 데스크톱의 디자인과 기능이 따로 갈라지지 않습니다.

## 핵심 원리

### 1. G(x): 하나의 진입점

사용자는 내부에 어떤 모델이 있는지 몰라도 됩니다. 사용자는 하나의 인터페이스에 입력을 보냅니다.

```text
입력 x
  ↓
G(x) Cloud AI Interface
  ↓
DER
  ↓
최종 출력 y
```

여기서 `G(x)`는 외부에서 보는 단일 AI 인터페이스입니다.

### 2. DER: 내부 실행 런타임

DER은 사용자의 요청을 받아서 어떤 expert를 쓸지 정하고 실행합니다.

```text
Request Normalizer
  ↓
Shared Context Loader
  ↓
Router / Planner
  ↓
Composition Builder
  ↓
Execution Engine
  ↓
Aggregator
  ↓
Judge / Verifier
  ↓
Memory Update
  ↓
Final Response
```

이 구조 덕분에 단일 모델 호출, 여러 모델 병렬 실행, fallback, judge 검증 같은 확장 기능을 단계적으로 붙일 수 있습니다.

### 3. Expert: 모든 모델을 같은 규격으로 감싸기

Ollama 모델, .NET 모델, ONNX 모델, 외부 API 모델은 내부 구현 방식이 다릅니다. 하지만 `Cloud AI Interface`에서는 모두 `Expert`라는 공통 단위로 다룹니다.

예를 들면 다음과 같습니다.

```text
OllamaExpert
MLNetExpert
DotNetCustomExpert
ExternalApiExpert
EmbeddingExpert
JudgeExpert
```

이렇게 하면 Router는 모델의 실제 구현을 몰라도, capability와 profile만 보고 실행할 expert를 고를 수 있습니다.

### 4. Composition Profile: 모델 조합 관리

여러 모델을 직접 합치는 것이 아니라, 실행 조합을 profile로 관리합니다.

예시:

```json
{
  "compositionId": "korean-reasoning-v1",
  "experts": [
    "mlnet-intent-classifier",
    "ollama-llama3-korean",
    "ollama-qwen-reasoner",
    "judge-model"
  ],
  "strategy": "parallel-then-judge",
  "fallback": ["general-chat-llm"]
}
```

이 방식은 다음 장점이 있습니다.

- 모델 파일을 억지로 병합하지 않아도 됩니다.
- 조합을 저장하고 재사용할 수 있습니다.
- 실패 시 fallback 모델을 쓸 수 있습니다.
- trace 데이터를 쌓아 나중에 더 좋은 조합을 선택할 수 있습니다.

## 폴더 설명

### `apps/web`

데스크톱 앱에서 실제로 표시되는 UI입니다.

중요 파일:

- `apps/web/index.html`
- `apps/web/src/main.js`
- `apps/web/src/styles.css`

WPF 앱은 이 웹 UI를 WebView2로 표시합니다. 따라서 디자인을 바꾸려면 주로 `apps/web`을 수정하면 됩니다.

### `ui/wpf`

Windows desktop app 셸입니다.

이 폴더는 복잡한 UI를 직접 만들지 않습니다. WebView2를 통해 `apps/web/index.html`을 데스크톱 창 안에 띄우는 역할을 합니다.

### `ui/api`

ASP.NET API 서버입니다. 기본 포트는 `5088`입니다.

대표 API:

```text
GET    /api/health
GET    /api/models
GET    /api/cloud-ai/interface
POST   /api/cloud-ai/compositions
GET    /api/market/models
POST   /api/market/models/{id}/download
DELETE /api/market/models/{id}
POST   /api/session/new
POST   /api/chat
POST   /api/chat/stream
POST   /api/tools/execute
```

UI는 이 API를 통해 모델 목록, AI 마켓, 채팅, 세션, Cloud AI catalog를 사용합니다.

### `Cloud AI interface`

이 프로젝트의 중심 런타임입니다.

주요 역할:

- 외부 요청을 표준 `CloudAIRequest`로 정규화
- expert registry 관리
- rule-based router와 scoring router
- composition profile 처리
- 병렬 실행 engine
- aggregator
- judge/verifier
- fallback/recovery
- trace/observability
- security/permission guard

사용자는 이 내부 구조를 몰라도 되지만, 시스템이 여러 모델을 하나의 AI처럼 다루는 핵심은 이 폴더에 있습니다.

### `runtime/ollama`

Ollama 로컬 서버와 모델 저장 위치입니다.

모델은 기본적으로 여기에 저장됩니다.

```text
runtime/ollama/server/models
```

AI 마켓에서 Ollama 모델을 다운로드하면 이 경로를 사용합니다.

### `runtime/dotnet`

.NET/ONNX/ML.NET 계열 모델 저장 위치입니다.

예:

```text
runtime/dotnet/models/onnx
runtime/dotnet/models/mlnet
```

### `publish`

배포 실행 폴더입니다.

사용자는 일반적으로 이 폴더의 `start-local-ai.cmd`만 실행하면 됩니다.

중요 파일:

- `publish/start-local-ai.cmd`
- `publish/start-local-ai.ps1`
- `publish/app/api`
- `publish/app/wpf`
- `publish/logs`

## AI 마켓

AI 마켓은 사용 가능한 로컬 AI 모델 목록을 보여주고, 다운로드/삭제를 제공합니다.

모델 종류는 크게 두 가지입니다.

### Ollama 모델

Ollama 모델은 `ollama pull` 방식으로 설치됩니다.

저장 위치:

```text
runtime/ollama/server/models
```

예:

- Llama 3.2
- Qwen2.5
- Qwen3
- Gemma 3
- Mistral
- Phi
- DeepSeek R1
- Code Llama
- StarCoder2
- nomic-embed-text
- BGE-M3
- Qwen3 Embedding

### .NET / ONNX 모델

직접 다운로드 가능한 모델은 `runtime/dotnet/models` 아래에 저장됩니다.

저장 위치:

```text
runtime/dotnet/models/onnx
runtime/dotnet/models/mlnet
```

이 모델들은 향후 .NET expert나 embedding expert로 연결할 수 있습니다.

## 실행 흐름 예시

사용자가 채팅창에 질문을 입력하면 다음 순서로 처리됩니다.

```text
1. Web UI가 입력을 받음
2. POST /api/chat 호출
3. API가 Cloud AI Interface에 요청 전달
4. Request Normalizer가 요청 정리
5. Router가 적절한 expert 선택
6. Execution Engine이 expert 실행
7. Aggregator가 결과 통합
8. Judge/Verifier가 품질 검증
9. 최종 응답을 UI에 표시
10. trace/log 기록
```

현재 MVP에서는 단일 모델 실행과 composition metadata 기반 실행이 중심입니다. 구조는 병렬 실행, judge, fallback, self-optimization으로 확장할 수 있게 만들어져 있습니다.

## 로그 위치

문제가 생기면 먼저 `publish/logs`를 확인합니다.

```text
publish/logs/api.stdout.log
publish/logs/api.stderr.log
publish/logs/ollama.startup.log
publish/logs/wpf.webview.log
```

각 로그의 의미:

- `api.stdout.log`: ASP.NET API 실행 로그
- `api.stderr.log`: API 오류 로그
- `ollama.startup.log`: Ollama 시작 관련 경고/오류
- `wpf.webview.log`: 데스크톱 앱 내부 WebView 로딩/JS 오류

## 다시 빌드하는 방법

개발자가 수정 후 배포 폴더를 갱신하려면 다음 명령을 실행합니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-publish.ps1 -IncludeWpf
```

이 명령은 다음을 갱신합니다.

- `publish/app/api`
- `publish/app/wpf`
- `publish/app/api/wwwroot`

## 상태 확인

API가 정상인지 확인하려면 다음 주소를 확인합니다.

```text
http://localhost:5088/api/health
```

필수 API가 살아 있어야 데스크톱 앱이 정상 동작합니다.

```text
http://localhost:5088/api/cloud-ai/interface
http://localhost:5088/api/market/models
```

## 자주 생기는 문제

### 데스크톱 앱은 켜졌는데 AI 마켓이나 모델 선택이 실패함

오래된 API가 이미 `5088` 포트를 잡고 있을 수 있습니다. `publish/start-local-ai.ps1`은 필수 endpoint를 검사하고, repo 내부의 오래된 API 프로세스면 다시 시작하도록 되어 있습니다.

그래도 실패하면 `publish/logs/api.stdout.log`와 `publish/logs/api.stderr.log`를 확인합니다.

### Ollama timeout 경고가 보임

Ollama 서버가 준비되는 데 오래 걸릴 수 있습니다. 이 경우 앱 실행 자체를 막지는 않고, 자세한 내용은 다음 파일에 기록됩니다.

```text
publish/logs/ollama.startup.log
```

API health에서 `ollama`가 `connected`이면 정상입니다.

### 모델 다운로드가 안 됨

확인할 것:

1. 인터넷 연결
2. Ollama 서버 실행 여부
3. `runtime/ollama/server/cli/ollama.exe` 존재 여부
4. 모델 저장 경로 쓰기 권한

### 화면은 뜨는데 디자인이 이상함

데스크톱 앱은 `apps/web/index.html`을 WebView2로 표시합니다. WebView 로딩 오류는 다음 파일에서 확인합니다.

```text
publish/logs/wpf.webview.log
```

## 설계 원칙

이 프로젝트는 다음 원칙을 기준으로 설계되었습니다.

1. 외부 사용자는 하나의 `Cloud AI Interface`만 본다.
2. 특정 모델에 종속되지 않는다.
3. 모든 모델은 `Expert` 뒤에 숨긴다.
4. 조합은 실제 모델 병합이 아니라 `Composition Profile`로 관리한다.
5. Expert는 `Shared Context`를 읽고 쓴다.
6. Router는 처음에는 단순 규칙 기반으로 시작하고, 나중에 scoring/self-optimization으로 확장한다.
7. Judge와 trace 없이 다중 모델 시스템을 만들지 않는다.

## 배포 관점 요약

사용자가 알아야 할 것은 간단합니다.

```text
1. publish/start-local-ai.cmd 실행
2. 데스크톱 앱에서 모델 선택
3. AI 마켓에서 필요한 모델 다운로드
4. 채팅 또는 모델 조합 사용
5. 문제가 있으면 publish/logs 확인
```

개발자는 다음 구조만 기억하면 됩니다.

```text
UI = apps/web
Desktop shell = ui/wpf
API = ui/api
AI runtime = Cloud AI interface
Local models = runtime
Distribution = publish
```

## 현재 MVP 범위

현재 구현된 MVP는 다음에 초점을 둡니다.

- G(x) 단일 인터페이스
- Expert 공통 구조
- Ollama adapter
- .NET/ONNX 모델 경로
- AI 마켓
- JSON/Runtime 기반 registry
- Rule-based routing
- Single/Pipeline 실행 기반
- Desktop app 배포 실행

향후 확장 가능한 영역:

- 병렬 실행 고도화
- Aggregator 전략 고도화
- Judge model 품질 평가
- fallback chain 자동화
- dynamic attach/detach
- health check dashboard
- scoring router
- self-optimization
- permission system 강화

