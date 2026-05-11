# Fine-Tuning Data

This folder stores code optimization training data.

Raw files:

- `optimization_events.jsonl`: automatically collected AI proposals. These are `bronze` by default.
- `human_reviewed.jsonl`: manually reviewed records. Use this for `silver` and `gold`.
- `code_optimization_train.jsonl`: generated training dataset.
- `dataset_manifest.json`: generated build summary.
- `gold.jsonl`: generated gold-only examples.
- `silver.jsonl`: generated silver-only examples.
- `splits/train.jsonl`, `splits/valid.jsonl`, `splits/test.jsonl`: generated train/eval split.

Quality grades:

- `gold`: tests passed, benchmark improved, and a human approved the final patch.
- `silver`: tests passed and a human approved the patch.
- `bronze`: AI proposal exists but validation is incomplete.

Training should use `gold` and selected `silver` records first. Avoid mixing `bronze` into fine-tuning unless the goal is exploratory data analysis.

Build:

```powershell
python scripts/build_dataset.py --write-template
python scripts/build_dataset.py
```

Record shape:

```json
{
  "task_type": "code_optimization",
  "language": "python",
  "user_goal": "속도를 개선하되 동작은 유지해줘.",
  "environment": {
    "device": "cpu",
    "os": "linux",
    "python_version": "3.12"
  },
  "code_before": "...",
  "context": {
    "related_files": [],
    "static_analysis": [],
    "rag_evidence": []
  },
  "ideal_answer": {
    "diagnosis": "...",
    "patch": "unified diff",
    "explanation": "...",
    "tests": ["pytest"],
    "risk_level": "low"
  },
  "code_after": "...",
  "eval": {
    "tests_passed": true,
    "benchmark_before": 1.25,
    "benchmark_after": 0.73,
    "human_approved": true
  }
}
```
