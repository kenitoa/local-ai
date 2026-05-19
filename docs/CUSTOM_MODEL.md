# Custom Ollama Model

Ollama는 `Modelfile`로 모델별 실행 조건을 만들 수 있습니다.

## Modelfile

```text
FROM llama3.1

PARAMETER temperature 0.3
PARAMETER num_ctx 4096

SYSTEM """
너는 한국어로 답하는 로컬 NAS/서버/개발 보조 AI다.
답변은 실무 절차 중심으로 작성한다.
"""
```

`num_ctx`는 컨텍스트 창 크기를 설정하는 파라미터입니다. Ollama `Modelfile` 문서에서 `PARAMETER num_ctx 4096` 같은 형식으로 설정할 수 있습니다.

## 생성

```powershell
ollama create local-assistant -f Modelfile
```

스크립트:

```powershell
.\create-custom-model.ps1
```

하드웨어 측정값으로 `num_ctx`를 자동 적용한 뒤 생성:

```powershell
.\create-custom-model.ps1 -AutoContext
```

## 실행

```powershell
ollama run local-assistant
```

스크립트에서 생성 후 바로 실행:

```powershell
.\create-custom-model.ps1 -RunAfterCreate
```

## Semantic Kernel

이후 Semantic Kernel에서는 다음처럼 사용합니다.

```text
modelId: "local-assistant"
```

`runtime/semantic-kernel/LocalAI.Api/appsettings.json`의 `Ollama.ModelId` 또는 `AiModel.ModelId` 값을 `local-assistant`로 바꾸면 됩니다.
