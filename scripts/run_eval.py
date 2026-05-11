from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_EVAL_DIR = ROOT_DIR / "data" / "eval_sets"
DEFAULT_OUTPUT = ROOT_DIR / "data" / "eval_sets" / "eval_report.json"


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_command(command: str, cwd: Path, timeout: int = 30) -> dict[str, object]:
    command = normalize_command(command)
    started = time.perf_counter()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(cwd) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        command,
        cwd=cwd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )
    return {
        "command": command,
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "elapsed_seconds": round(time.perf_counter() - started, 4),
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-2000:],
    }


def normalize_command(command: str) -> str:
    if command == "python" or command.startswith("python "):
        return command.replace("python", f'"{sys.executable}"', 1)
    return command


def copy_case(case_dir: Path, work_root: Path) -> Path:
    target = work_root / case_dir.name
    shutil.copytree(case_dir, target)
    return target


def apply_patch(case_workdir: Path, patch: str) -> dict[str, object]:
    if not patch.strip():
        return {"ok": False, "reason": "empty patch"}
    patch_path = case_workdir / "candidate.patch"
    patch_path.write_text(patch, encoding="utf-8", newline="\n")
    git_check = run_command(f"git apply --check {patch_path.name}", case_workdir)
    if not git_check["ok"]:
        return {"ok": False, "reason": "git apply --check failed", "detail": git_check}
    git_apply = run_command(f"git apply {patch_path.name}", case_workdir)
    return {"ok": bool(git_apply["ok"]), "detail": git_apply}


def explanation_score(candidate: dict[str, object]) -> dict[str, object]:
    required = ["summary", "risk_level", "bottleneck", "expected_effect", "test_command", "benchmark_command"]
    missing = [field for field in required if not candidate.get(field)]
    notes = candidate.get("notes", [])
    return {
        "ok": not missing and isinstance(notes, list),
        "missing": missing,
    }


def evaluate_case(case_dir: Path, candidate: dict[str, object] | None) -> dict[str, object]:
    metadata = read_json(case_dir / "metadata.json")
    candidate = candidate or {}
    with tempfile.TemporaryDirectory() as tmp:
        work_root = Path(tmp)
        case_workdir = copy_case(case_dir, work_root)
        run_command("git init", case_workdir)

        baseline_tests = run_command(str(metadata["test_command"]), case_workdir)
        baseline_bench = run_command(str(metadata["benchmark_command"]), case_workdir)
        patch_result = apply_patch(case_workdir, str(candidate.get("patch", "")))
        patched_tests = run_command(str(metadata["test_command"]), case_workdir) if patch_result["ok"] else None
        patched_bench = run_command(str(metadata["benchmark_command"]), case_workdir) if patch_result["ok"] else None
        ratio = (
            round(float(patched_bench["elapsed_seconds"]) / max(float(baseline_bench["elapsed_seconds"]), 0.0001), 4)
            if patched_bench
            else None
        )
        max_regression = float(metadata.get("max_regression_ratio", 1.05))

    return {
        "case_id": metadata["id"],
        "language": metadata["language"],
        "patch_applicable": patch_result["ok"],
        "baseline_tests_passed": baseline_tests["ok"],
        "patched_tests_passed": patched_tests["ok"] if patched_tests else False,
        "benchmark_ratio": ratio,
        "benchmark_ok": ratio is not None and ratio <= max_regression,
        "explanation": explanation_score(candidate),
        "details": {
            "patch": patch_result,
            "baseline_tests": baseline_tests,
            "patched_tests": patched_tests,
            "baseline_benchmark": baseline_bench,
            "patched_benchmark": patched_bench,
        },
    }


def find_cases(eval_dir: Path) -> list[Path]:
    return sorted(path for path in eval_dir.glob("*/*") if (path / "metadata.json").exists())


def load_candidates(path: Path | None) -> dict[str, dict[str, object]]:
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        return {str(item["case_id"]): item for item in data}
    return {str(key): value for key, value in data.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run patch/test/benchmark evaluation cases.")
    parser.add_argument("--eval-dir", type=Path, default=DEFAULT_EVAL_DIR)
    parser.add_argument("--candidates", type=Path, help="JSON file keyed by case_id with model outputs.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    candidates = load_candidates(args.candidates)
    results = [
        evaluate_case(case_dir, candidates.get(str(read_json(case_dir / "metadata.json")["id"])))
        for case_dir in find_cases(args.eval_dir)
    ]
    summary = {
        "case_count": len(results),
        "patch_applicable": sum(1 for item in results if item["patch_applicable"]),
        "tests_passed": sum(1 for item in results if item["patched_tests_passed"]),
        "benchmark_ok": sum(1 for item in results if item["benchmark_ok"]),
        "explanation_ok": sum(1 for item in results if item["explanation"]["ok"]),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
