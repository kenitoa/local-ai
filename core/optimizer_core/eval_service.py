class EvalService:
    def suggested_checks(self, language: str) -> list[str]:
        if language.lower() == "python":
            return ["ruff check .", "mypy .", "pytest", "python -m compileall ."]
        if language.lower() in {"javascript", "typescript"}:
            return ["npm test", "npm run lint"]
        return ["run existing test suite", "run benchmark before and after"]

    def test_command(self, language: str) -> str:
        if language.lower() == "python":
            return "pytest"
        if language.lower() in {"javascript", "typescript"}:
            return "npm test"
        return "run existing test suite"

    def benchmark_command(self, language: str) -> str:
        if language.lower() == "python":
            return "python -m pytest --benchmark-only"
        if language.lower() in {"javascript", "typescript"}:
            return "npm run benchmark"
        return "run existing benchmark"
