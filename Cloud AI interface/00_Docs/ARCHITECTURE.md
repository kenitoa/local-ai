# Cloud AI Interface Architecture

이 폴더는 사용자가 호출하는 단일 진입점 `G(x)`를 기준으로 DER 런타임을 구성한다.

## Final Runtime Flow

```text
Client / Unity / Web / API
        |
        v
G(x) Cloud AI Interface
        |
        v
Request Normalizer
        |
        v
Shared Context Loader
        |
        v
Router / Planner
        |
        v
Composition Builder
        |
        v
Execution Engine
   |        |          |             |
   v        v          v             v
Ollama   ML.NET     Vision      External API
Expert   Expert     Expert      Expert
   |        |          |             |
   +--------+----------+-------------+
        |
        v
Aggregator
        |
        v
Judge / Verifier
        |
        v
Memory Update
        |
        v
Final Response
```

## Directory Map

```text
Cloud AI interface/
  00_Docs/                  architecture notes and component map
  01_Interface/             G(x) API, request/response DTOs, orchestration service
  02_RequestNormalization/  request normalization, shared context loading, memory update
  03_Context/               shared runtime memory, task state, vectors, tool results
  04_Registry/              expert registry and attach/load lifecycle management
  05_Experts/               common expert contract and concrete expert adapters
  06_Routing/               rule-based router, scoring router, execution plan models
  07_Composition/           reusable composition profiles and plan resolver
  08_Execution/             execution engine, parallel runtime, limits and retries
  09_Aggregation/           result aggregation and candidate scoring
  10_Verification/          judge/verifier scoring and final validation
  11_Recovery/              fallback chains and failure recovery policy
  12_Observability/         trace records, sinks, timing, token and memory usage
  13_Optimization/          self-optimization records and recommendations
  14_Security/              expert permissions, request/result filtering, masking
  15_MVP/                   MVP readiness reporting
  Configuration/            JSON registry, composition, fallback, permission data
```

## Component Check

| Architecture component | Implementation |
| --- | --- |
| `G(x) Cloud AI Interface` | `01_Interface/ICloudAI.cs`, `01_Interface/CloudAIService.cs` |
| Request Normalizer | `02_RequestNormalization/DefaultCloudAIRequestNormalizer.cs` |
| Shared Context Loader | `02_RequestNormalization/DefaultSharedContextLoader.cs` |
| Router / Planner | `06_Routing/IRouter.cs`, `06_Routing/RuleBasedRouter.cs`, `06_Routing/ScoringRouter.cs` |
| Composition Builder | `07_Composition/CompositionPlanResolver.cs`, `07_Composition/CompositionProfileRouter.cs` |
| Execution Engine | `08_Execution/IExecutionEngine.cs`, `08_Execution/ParallelExecutionEngine.cs` |
| Expert adapters | `05_Experts/OllamaExpert.cs`, `05_Experts/MLNetExpert.cs`, `05_Experts/ExternalApiExpert.cs`, `05_Experts/EmbeddingExpert.cs` |
| Aggregator | `09_Aggregation/IAggregator.cs`, `09_Aggregation/ScoreBasedAggregator.cs` |
| Judge / Verifier | `10_Verification/IVerifier.cs`, `10_Verification/RuleBasedVerifier.cs` |
| Memory Update | `02_RequestNormalization/DefaultMemoryUpdater.cs` |
| Final Response | `01_Interface/CloudAIResponseFactory.cs`, `01_Interface/CloudAIResponse.cs` |
| Registry / attach-detach | `04_Registry/InMemoryExpertRegistry.cs`, `04_Registry/InMemoryExpertLifecycleManager.cs` |
| Observability / trace | `12_Observability/TraceRecorder.cs`, `12_Observability/RequestTrace.cs` |
| Security / isolation | `14_Security/DefaultExpertSecurityFilter.cs`, `14_Security/ExpertPermissions.cs` |
| MVP readiness | `15_MVP/MvpReadinessValidator.cs` |
