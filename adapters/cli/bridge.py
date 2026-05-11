from __future__ import annotations

from pathlib import Path

from core.optimizer_core import CodeOptimizerEngine, OptimizeRequest, OptimizeResult


class CliOptimizerBridge:
    def __init__(self) -> None:
        self.engine = CodeOptimizerEngine()

    def optimize(
        self,
        project_path: Path,
        target_files: list[str],
        goal: str,
        language: str,
        mode: str,
        project_id: str | None = None,
    ) -> OptimizeResult:
        request = OptimizeRequest(
            project_id=project_id or project_path.name or "local-project",
            project_path=project_path,
            target_files=target_files,
            user_goal=goal,
            language=language,
            mode=mode,
        )
        return self.engine.optimize(request)
