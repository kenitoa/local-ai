from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass


CUDA_TEST_IMAGE = "nvidia/cuda:12.8.0-base-ubuntu24.04"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def command(command_line: list[str], timeout: int = 60) -> Check:
    try:
        result = subprocess.run(
            command_line,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = (result.stdout + result.stderr).strip()
        return Check(" ".join(command_line), result.returncode == 0, output[-600:] or "no output")
    except FileNotFoundError as exc:
        return Check(" ".join(command_line), False, str(exc))
    except subprocess.TimeoutExpired:
        return Check(" ".join(command_line), False, "command timed out")


def main() -> None:
    checks = [
        Check("nvidia-smi exists", shutil.which("nvidia-smi") is not None, shutil.which("nvidia-smi") or "missing"),
        command(["nvidia-smi"], timeout=20),
        command(["docker", "info"], timeout=20),
        command(["docker", "run", "--rm", "--gpus", "all", CUDA_TEST_IMAGE, "nvidia-smi"], timeout=120),
        command(["docker", "compose", "-f", "docker/compose.yaml", "-f", "docker/compose.cuda.yaml", "config", "--services"], timeout=60),
    ]
    print(json.dumps([check.__dict__ for check in checks], indent=2, ensure_ascii=False))
    if not all(check.ok for check in checks):
        raise SystemExit("GPU host/runtime checks failed.")


if __name__ == "__main__":
    main()
