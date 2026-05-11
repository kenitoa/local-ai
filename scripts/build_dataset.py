from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
FINE_TUNE_DIR = ROOT_DIR / "data" / "fine_tune"
RAW_EVENTS = FINE_TUNE_DIR / "optimization_events.jsonl"
HUMAN_REVIEWED = FINE_TUNE_DIR / "human_reviewed.jsonl"
OUTPUT_PATH = FINE_TUNE_DIR / "code_optimization_train.jsonl"
MANIFEST_PATH = FINE_TUNE_DIR / "dataset_manifest.json"
SPLIT_DIR = FINE_TUNE_DIR / "splits"
GOLD_PATH = FINE_TUNE_DIR / "gold.jsonl"
SILVER_PATH = FINE_TUNE_DIR / "silver.jsonl"


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def quality(record: dict[str, object]) -> str:
    return str(record.get("quality", "bronze")).lower()


def to_training_example(record: dict[str, object]) -> dict[str, object]:
    context = record.get("context", {})
    ideal = record.get("ideal_answer", {})
    return {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a code optimization assistant. Return diagnosis, risk, tests, "
                    "and a unified diff patch. Never claim tests passed unless eval says so."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task_type": record.get("task_type"),
                        "language": record.get("language"),
                        "user_goal": record.get("user_goal"),
                        "environment": record.get("environment"),
                        "code_before": record.get("code_before"),
                        "context": context,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
            {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "diagnosis": ideal.get("diagnosis"),
                        "patch": ideal.get("patch"),
                        "explanation": ideal.get("explanation"),
                        "tests": ideal.get("tests"),
                        "risk_level": ideal.get("risk_level"),
                        "expected_effect": ideal.get("expected_effect"),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ],
        "metadata": {
            "source_id": record.get("id"),
            "quality": quality(record),
            "language": record.get("language"),
            "tests_passed": record.get("eval", {}).get("tests_passed") if isinstance(record.get("eval"), dict) else None,
        },
    }


def select_records(records: list[dict[str, object]], include_bronze: bool) -> list[dict[str, object]]:
    allowed = {"gold", "silver"}
    if include_bronze:
        allowed.add("bronze")
    return [record for record in records if quality(record) in allowed]


def split_records(
    records: list[dict[str, object]],
    seed: int = 42,
    train_ratio: float = 0.8,
    valid_ratio: float = 0.1,
) -> dict[str, list[dict[str, object]]]:
    shuffled = list(records)
    random.Random(seed).shuffle(shuffled)
    if len(shuffled) <= 2:
        return {"train": shuffled, "valid": [], "test": []}

    train_end = max(1, int(len(shuffled) * train_ratio))
    valid_end = max(train_end, int(len(shuffled) * (train_ratio + valid_ratio)))
    return {
        "train": shuffled[:train_end],
        "valid": shuffled[train_end:valid_end],
        "test": shuffled[valid_end:],
    }


def build_dataset(include_bronze: bool = False, seed: int = 42) -> dict[str, object]:
    raw = read_jsonl(RAW_EVENTS)
    reviewed = read_jsonl(HUMAN_REVIEWED)
    selected = select_records(raw + reviewed, include_bronze=include_bronze)
    examples = [to_training_example(record) for record in selected]
    gold_examples = [example for example in examples if example["metadata"]["quality"] == "gold"]
    silver_examples = [example for example in examples if example["metadata"]["quality"] == "silver"]
    splits = split_records(examples, seed=seed)

    write_jsonl(OUTPUT_PATH, examples)
    write_jsonl(GOLD_PATH, gold_examples)
    write_jsonl(SILVER_PATH, silver_examples)
    for split_name, split_examples in splits.items():
        write_jsonl(SPLIT_DIR / f"{split_name}.jsonl", split_examples)

    manifest = {
        "input_files": [str(RAW_EVENTS.relative_to(ROOT_DIR)), str(HUMAN_REVIEWED.relative_to(ROOT_DIR))],
        "output_file": str(OUTPUT_PATH.relative_to(ROOT_DIR)),
        "gold_file": str(GOLD_PATH.relative_to(ROOT_DIR)),
        "silver_file": str(SILVER_PATH.relative_to(ROOT_DIR)),
        "split_files": {
            split_name: str((SPLIT_DIR / f"{split_name}.jsonl").relative_to(ROOT_DIR))
            for split_name in splits
        },
        "record_count": len(examples),
        "quality_counts": {
            "gold": sum(1 for record in selected if quality(record) == "gold"),
            "silver": sum(1 for record in selected if quality(record) == "silver"),
            "bronze": sum(1 for record in selected if quality(record) == "bronze"),
        },
        "split_counts": {split_name: len(split_examples) for split_name, split_examples in splits.items()},
        "include_bronze": include_bronze,
        "seed": seed,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def write_templates() -> None:
    FINE_TUNE_DIR.mkdir(parents=True, exist_ok=True)
    review_template = {
        "id": "manual-review-example",
        "quality": "silver",
        "task_type": "code_optimization",
        "language": "python",
        "user_goal": "속도를 개선하되 동작은 유지해줘.",
        "environment": {"device": "cpu", "os": "linux", "python_version": "3.12"},
        "code_before": "def total(items):\n    result = 0\n    for item in items:\n        result = result + item\n    return result\n",
        "context": {"related_files": [], "static_analysis": [], "rag_evidence": []},
        "ideal_answer": {
            "diagnosis": "반복 덧셈 assignment를 더 간결한 in-place 표현으로 바꿀 수 있습니다.",
            "patch": "--- a/uploaded.py\n+++ b/uploaded.py\n@@ -1,5 +1,5 @@\n def total(items):\n     result = 0\n     for item in items:\n-        result = result + item\n+        result += item\n     return result\n",
            "explanation": "동작을 유지하면서 더 명확한 누적 표현으로 바꿉니다.",
            "tests": ["pytest"],
            "risk_level": "low",
            "expected_effect": "가독성 개선. 성능 개선은 작을 수 있습니다.",
        },
        "code_after": "def total(items):\n    result = 0\n    for item in items:\n        result += item\n    return result\n",
        "eval": {"tests_passed": True, "benchmark_before": 1.25, "benchmark_after": 1.20, "human_approved": True},
    }
    if not HUMAN_REVIEWED.exists():
        write_jsonl(HUMAN_REVIEWED, [review_template])


def main() -> None:
    parser = argparse.ArgumentParser(description="Build code optimization fine-tuning JSONL data.")
    parser.add_argument("--include-bronze", action="store_true", help="Include unverified AI proposals.")
    parser.add_argument("--write-template", action="store_true", help="Create human_reviewed.jsonl template.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.write_template:
        write_templates()
    manifest = build_dataset(include_bronze=args.include_bronze, seed=args.seed)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
