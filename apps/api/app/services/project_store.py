from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from app.config import settings


class ProjectStore:
    def __init__(self) -> None:
        self.root = Path(settings.data_dir) / "projects"
        self.index_path = self.root / "projects.json"

    def list_projects(self) -> list[dict[str, object]]:
        return self._load_projects()

    def create_project(self, name: str, description: str = "") -> dict[str, object]:
        projects = self._load_projects()
        project = {
            "id": str(uuid4()),
            "name": name,
            "description": description,
            "file_count": 0,
        }
        projects.append(project)
        self._save_projects(projects)
        (self._project_root(str(project["id"])) / "files").mkdir(parents=True, exist_ok=True)
        return project

    def save_file(
        self,
        project_id: str,
        path: str,
        content: str,
        language: str,
    ) -> dict[str, object]:
        safe_path = self._safe_relative_path(path)
        target = self._project_root(project_id) / "files" / safe_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self._upsert_file_count(project_id)
        return {
            "project_id": project_id,
            "path": str(safe_path).replace("\\", "/"),
            "language": language,
            "bytes": len(content.encode("utf-8")),
        }

    def read_project_files(self, project_id: str, paths: list[str] | None = None) -> list[dict[str, str]]:
        files_root = self._project_root(project_id) / "files"
        if not files_root.exists():
            return []

        wanted = {self._safe_relative_path(path) for path in paths or []}
        records: list[dict[str, str]] = []
        for file_path in files_root.rglob("*"):
            if not file_path.is_file():
                continue
            relative = file_path.relative_to(files_root)
            if wanted and relative not in wanted:
                continue
            records.append(
                {
                    "path": str(relative).replace("\\", "/"),
                    "content": file_path.read_text(encoding="utf-8", errors="replace"),
                }
            )
        return records

    def _load_projects(self) -> list[dict[str, object]]:
        if not self.index_path.exists():
            return []
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _save_projects(self, projects: list[dict[str, object]]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps(projects, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _upsert_file_count(self, project_id: str) -> None:
        projects = self._load_projects()
        files_root = self._project_root(project_id) / "files"
        file_count = len([path for path in files_root.rglob("*") if path.is_file()])
        for project in projects:
            if project["id"] == project_id:
                project["file_count"] = file_count
                break
        self._save_projects(projects)

    def _safe_relative_path(self, path: str) -> Path:
        relative = Path(path.replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Path must be relative and stay inside the project.")
        return relative

    def _project_root(self, project_id: str) -> Path:
        if not project_id or "/" in project_id or "\\" in project_id or ".." in project_id:
            raise ValueError("Invalid project id.")
        return self.root / project_id
