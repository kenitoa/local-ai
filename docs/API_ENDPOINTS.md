# Ollama REST API Endpoints

Base URL:

```text
http://localhost:11434
```

API base:

```text
http://localhost:11434/api
```

## 주요 엔드포인트

```text
GET  /api/tags
POST /api/chat
POST /api/generate
POST /api/embed
POST /api/embeddings
POST /v1/chat/completions
```

## GET /api/tags

설치된 로컬 모델 목록을 반환합니다.

```powershell
curl http://localhost:11434/api/tags
```

## POST /api/chat

대화형 응답용 엔드포인트입니다. 기본값은 스트리밍 응답입니다.

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

## POST /api/generate

단일 프롬프트 기반 텍스트 생성용 엔드포인트입니다.

```powershell
curl http://localhost:11434/api/generate -d '{
  "model": "llama3.1",
  "stream": false,
  "prompt": "안녕"
}'
```

## POST /api/embed

현재 Ollama 문서의 임베딩 엔드포인트입니다.

```powershell
curl http://localhost:11434/api/embed -d '{
  "model": "embeddinggemma",
  "input": "local ai"
}'
```

## POST /api/embeddings

일부 클라이언트나 이전 예제에서 사용하는 임베딩 호환 엔드포인트입니다. 신규 로컬 검증 스크립트는 공식 문서 기준인 `/api/embed`를 우선 사용합니다.

## POST /v1/chat/completions

Semantic Kernel이나 다른 OpenAI 호환 클라이언트와 붙일 때 사용할 수 있는 경로입니다.

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
