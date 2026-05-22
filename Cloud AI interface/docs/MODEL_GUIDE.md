# Operating Model Guide

운영용 권장 모델은 자동으로 전부 설치하지 않습니다. 아래 목록에서 현재 PC/NAS 성능과 용도에 맞는 모델만 골라 `models.selected.txt`에 넣고 다운로드합니다.

## 일반 대화

```text
llama3.1
qwen2.5
gemma2
mistral
```

## 코딩 보조

```text
codellama
qwen2.5-coder
deepseek-coder
```

## 임베딩/RAG

```text
nomic-embed-text
mxbai-embed-large
```

## RAG 최소 구성

```text
Chat Model      : qwen2.5 또는 llama3.1
Embedding Model : nomic-embed-text
Vector DB       : SQLite / Qdrant / Chroma / PostgreSQL pgvector
```

## 선택 / 선택 삭제

직접 편집:

```text
models.selected.txt
```

스크립트로 선택:

```powershell
.\select-models.ps1 -Select qwen2.5,nomic-embed-text
```

한글 별칭도 사용할 수 있습니다.

```powershell
.\select-models.ps1 -선택 qwen2.5,nomic-embed-text
```

한글 이름의 실행 파일도 제공합니다.

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

현재 선택 확인:

```powershell
.\select-models.ps1 -List
```

전체 선택 초기화:

```powershell
.\select-models.ps1 -Clear
```

다운로드:

```powershell
.\pull-models.ps1 -ModelFile .\models.selected.txt
```

Semantic Kernel의 채팅 모델은 `runtime/semantic-kernel/LocalAI.Api/appsettings.json`의 `Ollama.ModelId` 또는 `AiModel.ModelId`로 지정합니다. 임베딩 모델은 RAG 구현에서 별도 옵션으로 분리하는 것을 권장합니다.
