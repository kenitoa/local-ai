from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.optimizer_core.exceptions import EmptyTargetFiles, TargetFileReadError


@dataclass(slots=True)
class OptimizeRequest:
    project_id: str
    project_path: Path
    target_files: list[str]
    user_goal: str
    language: str = "python"
    mode: str = "hybrid"  # deterministic | local_llm | hybrid

    def read_target_code(self) -> str:
        if not self.target_files:
            raise EmptyTargetFiles("OptimizeRequest.target_files must contain at least one file.")
        chunks: list[str] = []
        for target_file in self.target_files:
            file_path = (self.project_path / target_file).resolve()
            if not file_path.is_file():
                raise TargetFileReadError(f"Target file not found: {file_path}")
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                raise TargetFileReadError(f"Could not read target file: {file_path}") from exc
            chunks.append(content if len(self.target_files) == 1 else f"# file: {target_file}\n{content}")
        return "\n\n".join(chunks)

    @property
    def primary_target(self) -> str:
        return self.target_files[0] if self.target_files else self.project_id
