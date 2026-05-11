# Evaluation Sets

Evaluation cases are separate from training data.

Layout:

```text
data/eval_sets/
|-- python_small/
|-- python_medium/
|-- js_small/
`-- real_world_cases/
```

Each case:

```text
case_001/
|-- input.py
|-- tests/
|-- benchmark.py
|-- expected_notes.md
`-- metadata.json
```

Evaluation checks:

- Patch can be applied.
- Tests pass.
- Benchmark improves or does not regress.
- Memory does not regress if measured.
- Readability does not get worse.
- Existing public API is preserved.
- Explanation is accurate and includes risk/test guidance.
