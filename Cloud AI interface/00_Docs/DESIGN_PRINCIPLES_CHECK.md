# Design Principles Check

검증 기준은 `G(x)`를 단일 외부 인터페이스로 두고, DER 내부에서 registry, router, executor, aggregator, judge, trace를 조합한다는 원칙이다.

## Result

| No. | Principle | Status | Evidence |
| --- | --- | --- | --- |
| 1 | `G(x)` is not bound to a specific model. | Pass | `01_Interface/CloudAIService.cs` depends on `IExpertRegistry`, `IRouter`, `IExecutionEngine`, `IAggregator`, `IVerifier`, `ITraceRecorder`, not concrete model adapters. |
| 2 | All models are hidden behind the expert interface. | Pass | All concrete expert adapters in `05_Experts/` inherit `ExpertAdapterBase`, which implements `IExpert`. |
| 3 | Expert combinations are managed as Composition Profiles. | Pass | `CloudAIServiceFactory` routes MVP2, MVP4, and self-optimization fallback through `CompositionProfileRouter`; default profiles are loaded from `Configuration/composition-profiles.json`. |
| 4 | Every expert reads and writes shared context. | Pass | `ParallelExecutionEngine` passes the same `RuntimeContext` into every `ExpertRequest`; `ExpertAdapterBase` records `PreviousResults` and `ExecutionHistory`. |
| 5 | Router starts simple and can later become learned/scored. | Pass | MVP1 keeps `RuleBasedRouter`; MVP2+ uses `CompositionProfileRouter`; MVP4+ keeps scoring as fallback through `ScoringRouter`; self-optimization wraps profile routing. |
| 6 | Do not build multi-model execution without judge/verifier. | Pass | `CloudAIService` always runs `RuleBasedVerifier`; multi-expert composition profiles use `RequiresJudge` and `CompositionPlanResolver` inserts a judge step for judge-required parallel profiles. |
| 7 | Always leave trace data. | Pass | `TraceRecorder` records `RequestTrace`; `DefaultMemoryUpdater` stores `lastTrace`; traces include initial, recovery, and actually executed expert ids. |

## Verified Cases

```text
default CreateAsync()                 -> general-chat-v1
MVP2 code request                     -> code-pipeline-v1 with judge
MVP4 code request                     -> code-pipeline-v1 with profile-first routing
self-optimization without history      -> general-chat-v1 through profile fallback
explicit parallel-vote-code-v1 request -> parallel vote plus judge-model
```

## Fixed During Check

```text
MVP4 previously bypassed CompositionProfileRouter and used ScoringRouter directly.
CompositionProfileRouter previously fell back to rule-based routing when CompositionId was omitted.
RuleBasedResponseExpert previously implemented IExpert directly and did not record through ExpertAdapterBase.
Trace selectedExperts previously omitted recovery-plan experts.
Default factory creation previously did not automatically load bundled Configuration JSON files.
parallel-vote-code-v1 previously did not force a judge step.
```
