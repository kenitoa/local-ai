from __future__ import annotations

import argparse
import sys
from pathlib import Path

from adapters.cli.bridge import CliOptimizerBridge
from adapters.cli.formatters import result_to_json, result_to_text, write_patch
from core.optimizer_core import OptimizerCoreError, UnsupportedOptimizationMode


DEFAULT_GOAL = "Improve performance while preserving behavior."
MODE_CHOICES = ("deterministic", "local_llm", "hybrid")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.interactive:
        args = fill_interactive_args(args)
    try:
        project_path = resolve_project(args.project)
        targets = normalize_targets(args.target)
        if not targets:
            parser.error("at least one --target is required")
        language = args.language or infer_language(targets[0])
        result = CliOptimizerBridge().optimize(
            project_path=project_path,
            target_files=targets,
            goal=args.goal,
            language=language,
            mode=args.mode,
            project_id=args.project_id,
        )
    except (OptimizerCoreError, UnsupportedOptimizationMode, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.patch_out:
        write_patch(Path(args.patch_out), result.patch)
    if args.json:
        print(result_to_json(result))
    else:
        print(result_to_text(result, show_patch=not args.no_patch))
        if args.patch_out:
            print(f"\nPatch written to: {args.patch_out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-code-optimize",
        description="Run the local code optimizer core without FastAPI or a web server.",
    )
    parser.add_argument("project", nargs="?", default=".", help="Project directory to inspect.")
    parser.add_argument("--target", action="append", default=[], help="Target file path, relative to project.")
    parser.add_argument("--goal", default=DEFAULT_GOAL, help="Optimization goal.")
    parser.add_argument("--mode", default="hybrid", choices=MODE_CHOICES, help="Optimization mode.")
    parser.add_argument("--language", help="Language override. Defaults to target file extension.")
    parser.add_argument("--project-id", help="Stable project id for local indexes.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--patch-out", help="Write the generated unified diff to this path.")
    parser.add_argument("--no-patch", action="store_true", help="Hide patch text from human-readable output.")
    parser.add_argument("--interactive", action="store_true", help="Prompt for missing project, target, and goal.")
    return parser


def fill_interactive_args(args: argparse.Namespace) -> argparse.Namespace:
    if not args.project or args.project == ".":
        project = input("Project path [.]: ").strip()
        args.project = project or "."
    if not args.target:
        target = input("Target file: ").strip()
        args.target = [target] if target else []
    if args.goal == DEFAULT_GOAL:
        goal = input(f"Goal [{DEFAULT_GOAL}]: ").strip()
        args.goal = goal or DEFAULT_GOAL
    return args


def resolve_project(project: str) -> Path:
    path = Path(project).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"Project directory not found: {path}")
    return path


def normalize_targets(values: list[str]) -> list[str]:
    targets: list[str] = []
    for value in values:
        targets.extend(item.strip().replace("\\", "/") for item in value.split(",") if item.strip())
    return targets


def infer_language(target: str) -> str:
    suffix = Path(target).suffix.lower()
    return {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
    }.get(suffix, "text")


if __name__ == "__main__":
    raise SystemExit(main())
