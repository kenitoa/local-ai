from __future__ import annotations

import ctypes
import json
import os
import platform
import socket
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
RUNTIME_ENV = ROOT_DIR / ".runtime.env"
RUNTIME_JSON = ROOT_DIR / ".runtime.json"
MODEL_DIR = "/models"
HF_HOME = "/models/.cache/huggingface"
CUDA_TEST_IMAGE = "nvidia/cuda:12.8.0-base-ubuntu24.04"


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    returncode: int
    output: str


@dataclass(frozen=True)
class RuntimeProfile:
    ai_device: str
    llm_backend: str
    compose_files: str
    model_runtime: str
    llm_model_path: str


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    value: str


def has_command(command: str) -> bool:
    return shutil.which(command) is not None


def command_ok(command: list[str], timeout: int = 20) -> CommandResult:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        output = (result.stdout + result.stderr).strip()
        return CommandResult(result.returncode == 0, result.returncode, output)
    except FileNotFoundError as exc:
        return CommandResult(False, 127, str(exc))
    except subprocess.TimeoutExpired as exc:
        output = ((exc.stdout or "") + (exc.stderr or "")).strip()
        return CommandResult(False, 124, output or "command timed out")


def has_nvidia_gpu() -> bool:
    if not has_command("nvidia-smi"):
        return False
    return command_ok(["nvidia-smi"], timeout=15).ok


def total_ram_gb() -> float:
    if platform.system() == "Windows":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.ullTotalPhys / 1024**3
        return 0.0

    if hasattr(os, "sysconf"):
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
        return (page_size * page_count) / 1024**3

    return 0.0


def docker_available() -> bool:
    return has_command("docker") and command_ok(["docker", "info"], timeout=20).ok


def docker_gpu_works() -> bool:
    if not docker_available() or not has_nvidia_gpu():
        return False
    result = command_ok(
        [
            "docker",
            "run",
            "--rm",
            "--gpus",
            "all",
            CUDA_TEST_IMAGE,
            "nvidia-smi",
        ],
        timeout=90,
    )
    return result.ok


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def select_profile(nvidia_gpu: bool, docker_gpu: bool) -> RuntimeProfile:
    if nvidia_gpu and docker_gpu:
        return RuntimeProfile(
            ai_device="cuda",
            llm_backend="vllm",
            compose_files="docker/compose.yaml:docker/compose.cuda.yaml",
            model_runtime="vllm-offline",
            llm_model_path="/models/base/code-model",
        )

    return RuntimeProfile(
        ai_device="cpu",
        llm_backend="llama_cpp",
        compose_files="docker/compose.yaml:docker/compose.cpu.yaml",
        model_runtime="llama-cpp-python",
        llm_model_path="/models/gguf/code-model-q4.gguf",
    )


def write_runtime_files(profile: RuntimeProfile, checks: list[Check]) -> None:
    env_lines = [
        f"AI_DEVICE={profile.ai_device}",
        f"LLM_BACKEND={profile.llm_backend}",
        f"COMPOSE_FILES={profile.compose_files}",
        f"MODEL_RUNTIME={profile.model_runtime}",
        f"LLAMA_CPP_MODEL_PATH={profile.llm_model_path if profile.ai_device == 'cpu' else '/models/gguf/code-model-q4.gguf'}",
        f"VLLM_MODEL_PATH={profile.llm_model_path if profile.ai_device == 'cuda' else '/models/base/code-model'}",
        f"MODEL_DIR={MODEL_DIR}",
        f"HF_HOME={HF_HOME}",
    ]
    RUNTIME_ENV.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
    RUNTIME_JSON.write_text(
        json.dumps(
            {
                "profile": profile.__dict__,
                "checks": [check.__dict__ for check in checks],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def print_checks(checks: list[Check]) -> None:
    for index, check in enumerate(checks, start=1):
        state = "ok" if check.ok else "warn"
        print(f"{index:02d}. [{state}] {check.name}: {check.value}")


def print_runtime(profile: RuntimeProfile) -> None:
    print()
    print("Selected runtime:")
    print(f"AI_DEVICE={profile.ai_device}")
    print(f"LLM_BACKEND={profile.llm_backend}")
    print(f"COMPOSE_FILES={profile.compose_files}")
    print(f"MODEL_RUNTIME={profile.model_runtime}")
    print(f"LLM_MODEL_PATH={profile.llm_model_path}")
    print(f"MODEL_DIR={MODEL_DIR}")
    print(f"HF_HOME={HF_HOME}")
    print()
    print(f"Wrote {RUNTIME_ENV.relative_to(ROOT_DIR)}")
    print(f"Wrote {RUNTIME_JSON.relative_to(ROOT_DIR)}")


def main() -> None:
    docker_command = has_command("docker")
    docker_running = docker_available()
    nvidia_command = has_command("nvidia-smi")
    nvidia_gpu = has_nvidia_gpu()
    docker_gpu = docker_gpu_works()
    occupied_ports = [str(port) for port in (3000, 8000) if port_open(port)]
    profile = select_profile(nvidia_gpu=nvidia_gpu, docker_gpu=docker_gpu)

    checks = [
        Check("OS", True, f"{platform.system()} {platform.release()}"),
        Check("CPU cores", (os.cpu_count() or 0) >= 2, str(os.cpu_count() or "unknown")),
        Check("RAM", total_ram_gb() >= 4, f"{total_ram_gb():.1f} GB"),
        Check("Docker command", docker_command, "found" if docker_command else "missing"),
        Check("Docker daemon", docker_running, "ready" if docker_running else "not reachable"),
        Check("NVIDIA command", nvidia_command, "found" if nvidia_command else "missing"),
        Check("nvidia-smi", nvidia_gpu, "usable" if nvidia_gpu else "not available"),
        Check("Docker GPU access", docker_gpu, "usable" if docker_gpu else "not available"),
        Check(
            "Optional web/API ports",
            True,
            "free" if not occupied_ports else f"occupied but only needed with --profile web: {', '.join(occupied_ports)}",
        ),
        Check("Compose profile", True, profile.compose_files),
    ]

    write_runtime_files(profile, checks)
    print("AI Code Optimizer preflight")
    print(f"Python: {platform.python_version()}")
    print_checks(checks)
    print_runtime(profile)

    if not docker_running:
        raise SystemExit("Docker is required before running docker compose.")


if __name__ == "__main__":
    main()
