"""local-ai hardware-detector (Step 6).

CPU/RAM/GPU/저장공간 등을 감지하고 실행 모드(gpu/cpu)를 결정한다.
결과는 backend ``/api/v1/hardware/profile`` 로 업서트한다.

감지 항목:
    - CPU 모델/코어 수
    - RAM 총량
    - GPU 존재 여부, 제조사, 모델, VRAM
    - CUDA / DirectML 사용 가능 여부
    - 컨테이너 내부에서 GPU 접근 가능 여부
    - 저장공간(총량/여유)

실행 모드 결정:
    1) NVIDIA GPU 가 보이고 컨테이너에서 접근 가능 → ``gpu``
    2) GPU 가 있지만 컨테이너 접근 실패         → ``cpu`` (fallback + 사유 기록)
    3) GPU 없음                                  → ``cpu``
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import shutil
import socket
import subprocess
from datetime import datetime
from typing import Any

import psutil
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

SERVICE_NAME = os.getenv("SERVICE_NAME", "hardware-detector")
LOG_DIR = "/app/logs"
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f"{SERVICE_NAME}.log")),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(SERVICE_NAME)

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000").rstrip("/")
STORAGE_PATH = os.getenv("STORAGE_PATH", "/app/data")
PUSH_ON_STARTUP = os.getenv("PUSH_ON_STARTUP", "1") == "1"

app = FastAPI(title=f"local-ai {SERVICE_NAME}")

_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 감지 헬퍼
# ---------------------------------------------------------------------------
def _safe_run(cmd: list[str], timeout: float = 3.0) -> tuple[int, str, str]:
    """외부 명령을 안전하게 실행한다. (rc, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return 127, "", "not found"
    except Exception as exc:  # noqa: BLE001
        return 1, "", str(exc)


def detect_cpu() -> dict[str, Any]:
    model = platform.processor() or platform.machine() or "unknown"
    if os.path.exists("/proc/cpuinfo"):
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8") as fp:
                for line in fp:
                    if line.lower().startswith("model name"):
                        model = line.split(":", 1)[1].strip()
                        break
        except OSError:
            pass
    return {
        "model": model,
        "cores_logical": psutil.cpu_count(logical=True) or 0,
        "cores_physical": psutil.cpu_count(logical=False) or 0,
        "arch": platform.machine(),
    }


def detect_ram() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    return {
        "total_mb": int(vm.total / (1024 * 1024)),
        "available_mb": int(vm.available / (1024 * 1024)),
    }


def detect_storage(path: str) -> dict[str, Any]:
    target = path if os.path.exists(path) else "/"
    usage = shutil.disk_usage(target)
    return {
        "path": target,
        "total_gb": round(usage.total / (1024 ** 3), 2),
        "free_gb": round(usage.free / (1024 ** 3), 2),
        "used_gb": round(usage.used / (1024 ** 3), 2),
    }


def detect_nvidia_via_smi() -> list[dict[str, Any]]:
    """``nvidia-smi --query-gpu=...`` 로 GPU 목록 조회."""
    rc, out, err = _safe_run([
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ])
    if rc != 0 or not out.strip():
        log.debug("nvidia-smi unavailable rc=%s err=%s", rc, err.strip())
        return []
    gpus: list[dict[str, Any]] = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            vram_mb = int(float(parts[1]))
        except ValueError:
            vram_mb = 0
        gpus.append({
            "name": parts[0],
            "vram_mb": vram_mb,
            "driver_version": parts[2] if len(parts) > 2 else None,
            "vendor": "nvidia",
        })
    return gpus


def detect_directml_available() -> bool:
    """DirectML 가용 여부(주로 Windows). Linux 컨테이너에서는 보통 False."""
    if platform.system() != "Windows":
        return False
    try:
        import torch_directml  # type: ignore[import-not-found]  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def detect_cuda_available(nvidia_gpus: list[dict[str, Any]]) -> bool:
    if not nvidia_gpus:
        return False
    for cand in ("/usr/local/cuda", "/usr/lib/x86_64-linux-gnu/libcuda.so.1"):
        if os.path.exists(cand):
            return True
    return True


def detect_docker_gpu_ok() -> tuple[bool, str]:
    """컨테이너 내부에서 NVIDIA 디바이스에 접근할 수 있는지 점검."""
    dev_nodes: list[str] = []
    if os.path.isdir("/dev"):
        try:
            dev_nodes = [n for n in os.listdir("/dev") if n.startswith("nvidia")]
        except OSError:
            dev_nodes = []
    if dev_nodes:
        rc, _, err = _safe_run(["nvidia-smi", "-L"])
        if rc == 0:
            return True, "nvidia-smi -L ok"
        return False, f"device present but nvidia-smi failed: {err.strip()}"
    if os.getenv("NVIDIA_VISIBLE_DEVICES"):
        return False, "NVIDIA_VISIBLE_DEVICES set but no /dev/nvidia* nodes"
    return False, "no nvidia devices in container"


def decide_run_mode(
    *,
    nvidia_gpus: list[dict[str, Any]],
    docker_gpu_ok: bool,
) -> tuple[str, str]:
    if nvidia_gpus and docker_gpu_ok:
        return "gpu", "nvidia gpu accessible inside container"
    if nvidia_gpus and not docker_gpu_ok:
        return "cpu", "nvidia gpu present but docker access failed -> cpu fallback"
    return "cpu", "no usable gpu detected"


def _fingerprint(profile: dict[str, Any]) -> str:
    canonical = {
        "host": profile.get("host_name"),
        "cpu": profile.get("cpu_model"),
        "cores": profile.get("cpu_cores"),
        "ram_mb": profile.get("ram_mb"),
        "gpu": profile.get("gpu_model"),
        "vram_mb": profile.get("gpu_vram_mb"),
    }
    blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def collect_profile() -> dict[str, Any]:
    cpu = detect_cpu()
    ram = detect_ram()
    storage = detect_storage(STORAGE_PATH)
    nvidia_gpus = detect_nvidia_via_smi()
    docker_gpu_ok, gpu_access_note = detect_docker_gpu_ok()
    cuda_ok = detect_cuda_available(nvidia_gpus)
    directml_ok = detect_directml_available()
    run_mode, reason = decide_run_mode(
        nvidia_gpus=nvidia_gpus,
        docker_gpu_ok=docker_gpu_ok,
    )

    primary_gpu = nvidia_gpus[0] if nvidia_gpus else None
    profile: dict[str, Any] = {
        "host_name": socket.gethostname(),
        "os_name": platform.system(),
        "os_version": platform.release(),
        "cpu_model": cpu["model"],
        "cpu_cores": cpu["cores_logical"],
        "ram_mb": ram["total_mb"],
        "gpu_present": bool(nvidia_gpus),
        "gpu_vendor": (primary_gpu or {}).get("vendor") if nvidia_gpus else None,
        "gpu_model": (primary_gpu or {}).get("name") if nvidia_gpus else None,
        "gpu_vram_mb": (primary_gpu or {}).get("vram_mb") if nvidia_gpus else None,
        "accelerator": "cuda" if (run_mode == "gpu" and cuda_ok) else "cpu",
        "cuda_available": cuda_ok,
        "directml_available": directml_ok,
        "docker_gpu_ok": docker_gpu_ok,
        "storage_total_gb": storage["total_gb"],
        "storage_free_gb": storage["free_gb"],
        "run_mode": run_mode,
        "detected_at": datetime.utcnow().isoformat() + "Z",
        "details_json": {
            "cpu": cpu,
            "ram": ram,
            "storage": storage,
            "gpus": nvidia_gpus,
            "gpu_access_note": gpu_access_note,
            "run_mode_reason": reason,
        },
    }
    profile["fingerprint"] = _fingerprint(profile)
    return profile


def push_profile(profile: dict[str, Any]) -> dict[str, Any] | None:
    url = f"{BACKEND_URL}/api/v1/hardware/profile"
    try:
        resp = requests.post(url, json=profile, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to push hardware profile: %s", exc)
        return None


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------
@app.get("/")
def root():
    return {"service": SERVICE_NAME, "status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/detect")
def detect_now():
    """즉시 감지 결과 반환(저장 안 함)."""
    return collect_profile()


@app.post("/api/v1/detect")
def detect_and_store():
    """감지 후 backend 에 업서트."""
    profile = collect_profile()
    pushed = push_profile(profile)
    if pushed is None:
        raise HTTPException(502, "failed to persist hardware profile via backend")
    return {"profile": profile, "stored": pushed}


@app.get("/api/v1/run-mode")
def run_mode_now():
    profile = collect_profile()
    return {
        "run_mode": profile["run_mode"],
        "reason": profile["details_json"]["run_mode_reason"],
        "gpu_present": profile["gpu_present"],
        "docker_gpu_ok": profile["docker_gpu_ok"],
        "cuda_available": profile["cuda_available"],
        "directml_available": profile["directml_available"],
    }


@app.on_event("startup")
def _startup():
    log.info("%s service started; BACKEND_URL=%s", SERVICE_NAME, BACKEND_URL)
    if not PUSH_ON_STARTUP:
        return
    try:
        profile = collect_profile()
        log.info(
            "detected: cpu=%s cores=%s ram=%sMB gpu=%s run_mode=%s",
            profile["cpu_model"], profile["cpu_cores"], profile["ram_mb"],
            profile["gpu_model"], profile["run_mode"],
        )
        push_profile(profile)
    except Exception as exc:  # noqa: BLE001
        log.warning("startup detection failed: %s", exc)
