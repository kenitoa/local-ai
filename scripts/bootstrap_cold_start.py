"""local-ai cold-start bootstrap.

이 프로젝트는 외부 사전학습 모델을 카탈로그처럼 사용하지 않는다.
유일하게 허용되는 외부 다운로드는 *콜드스타트 베이스 1개* 뿐이며,
이 스크립트가 그 1회 다운로드를 책임진다. 한 번 받고 나면 이후 모든
학습/추론은 ``models/local/`` 아래의 자기 가중치만 사용한다.

동작 순서
---------
1. ``BOOTSTRAP_ALLOW_DOWNLOAD`` 가 0/false 이면 즉시 종료(완전 오프라인 모드).
2. ``COLD_START_BASE_ID`` (기본 ``Qwen/Qwen2.5-Coder-1.5B``) 를 읽는다.
3. ``models/local/base/<safe-name>/`` 가 이미 비어있지 않으면 skip.
4. ``huggingface_hub.snapshot_download`` 로 *해당 ID 만* 다운로드.
   다른 어떤 모델도 받지 않는다.
5. ``models/local/state.json`` 에 다음을 기록::

       {
         "cold_start": {
           "base_id": "Qwen/Qwen2.5-Coder-1.5B",
           "params_b": 1.5,
           "downloaded_at": "2026-04-30T12:34:56Z",
           "path": "models/local/base/Qwen__Qwen2.5-Coder-1.5B",
           "files": ["config.json", "tokenizer.json", ...],
           "size_bytes": 3120384122
         },
         "policy": "cold-start-only"
       }

   이 파일이 존재하면 launcher / model-server 가 "콜드스타트가 끝났다"고 인지한다.

CLI
---
사용 예::

    python scripts/bootstrap_cold_start.py
    python scripts/bootstrap_cold_start.py --status
    python scripts/bootstrap_cold_start.py --force        # 재다운로드
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 경로/환경
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = Path(os.environ.get("MODELS_DIR", REPO_ROOT / "models")).resolve()
LOCAL_DIR = MODELS_DIR / "local"
BASE_DIR = LOCAL_DIR / "base"
STATE_FILE = LOCAL_DIR / "state.json"

DEFAULT_BASE_ID = os.environ.get("COLD_START_BASE_ID", "Qwen/Qwen2.5-Coder-1.5B")
DEFAULT_BASE_PARAMS_B = float(os.environ.get("COLD_START_BASE_PARAMS_B", "1.5"))
ALLOW_DOWNLOAD = os.environ.get("BOOTSTRAP_ALLOW_DOWNLOAD", "1").lower() not in (
    "0", "false", "no", "off", ""
)

# huggingface_hub 다운로드 시 무시할 거대 사이드카(원본 fp32 가중치 등)
DEFAULT_IGNORE_PATTERNS = [
    "*.bin",          # 가능하면 safetensors 만 받는다
    "*.gguf",
    "*.onnx",
    "original/*",
    "consolidated*",
]


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------
def _safe_name(model_id: str) -> str:
    return model_id.replace("/", "__").replace(":", "_")


def _now_utc() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def _list_files(path: Path, limit: int = 32) -> list[str]:
    files = []
    for p in sorted(path.rglob("*")):
        if p.is_file():
            files.append(str(p.relative_to(path)).replace("\\", "/"))
            if len(files) >= limit:
                break
    return files


def _read_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return {}


def _write_state(state: dict[str, Any]) -> None:
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _is_already_downloaded(target: Path) -> bool:
    """대상 디렉터리에 config.json + 가중치 파일이 있으면 받은 것으로 간주."""
    if not target.is_dir():
        return False
    if not (target / "config.json").is_file():
        return False
    for pat in ("*.safetensors", "*.bin", "*.gguf", "*.onnx"):
        for _ in target.rglob(pat):
            return True
    return False


# ---------------------------------------------------------------------------
# 다운로드
# ---------------------------------------------------------------------------
def download_cold_start(
    *,
    base_id: str,
    params_b: float,
    target: Path,
    force: bool,
) -> dict[str, Any]:
    if not force and _is_already_downloaded(target):
        return {
            "status":  "already-present",
            "base_id": base_id,
            "path":    str(target.relative_to(REPO_ROOT)),
            "files":   _list_files(target),
            "size_bytes": _dir_size(target),
        }

    if not ALLOW_DOWNLOAD:
        raise SystemExit(
            "BOOTSTRAP_ALLOW_DOWNLOAD=0 → 외부 다운로드가 차단되어 있습니다. "
            "오프라인 모드에서는 사전에 해당 디렉터리를 수동 배치하세요:\n"
            f"  {target}"
        )

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # noqa: BLE001
        raise SystemExit(
            "huggingface_hub 가 설치되어 있지 않습니다. "
            "`pip install huggingface_hub` 후 다시 실행하세요."
        ) from exc

    target.mkdir(parents=True, exist_ok=True)
    print(f"[cold-start] downloading {base_id} → {target}")
    snapshot_download(
        repo_id=base_id,
        local_dir=str(target),
        local_dir_use_symlinks=False,
        ignore_patterns=DEFAULT_IGNORE_PATTERNS,
        # huggingface 외 어떤 mirror 도 사용하지 않는다.
        # 토큰이 필요한 private repo 는 일부러 지원하지 않는다.
    )

    return {
        "status":  "downloaded",
        "base_id": base_id,
        "params_b": params_b,
        "path":    str(target.relative_to(REPO_ROOT)),
        "files":   _list_files(target),
        "size_bytes": _dir_size(target),
        "downloaded_at": _now_utc(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def cmd_status() -> int:
    state = _read_state()
    if not state.get("cold_start"):
        print("cold-start: not initialized.")
        return 1
    cs = state["cold_start"]
    print("cold-start: ready")
    print(f"  base_id       : {cs.get('base_id')}")
    print(f"  params_b      : {cs.get('params_b')}")
    print(f"  path          : {cs.get('path')}")
    print(f"  size_bytes    : {cs.get('size_bytes')}")
    print(f"  downloaded_at : {cs.get('downloaded_at')}")
    return 0


def cmd_run(force: bool, base_id: str, params_b: float) -> int:
    target = BASE_DIR / _safe_name(base_id)
    info = download_cold_start(
        base_id=base_id,
        params_b=params_b,
        target=target,
        force=force,
    )

    state = _read_state()
    if info["status"] == "already-present" and "downloaded_at" not in info:
        # 기존 state 가 있으면 그 시각을 보존
        prev = state.get("cold_start", {})
        info["downloaded_at"] = prev.get("downloaded_at") or _now_utc()
        info["params_b"] = prev.get("params_b", params_b)
    state["cold_start"] = info
    state["policy"] = "cold-start-only"
    _write_state(state)

    print(f"[cold-start] {info['status']}: {info['base_id']}")
    print(f"            path = {info['path']}  size = {info['size_bytes']:,} bytes")
    print(f"            state file = {STATE_FILE.relative_to(REPO_ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="local-ai cold-start bootstrap (콜드스타트 베이스 1회 다운로드)"
    )
    parser.add_argument("--status", action="store_true", help="현재 상태만 확인")
    parser.add_argument("--force",  action="store_true", help="이미 받았어도 다시 받기")
    parser.add_argument("--base-id", default=DEFAULT_BASE_ID,
                        help=f"콜드스타트 모델 ID (기본: {DEFAULT_BASE_ID})")
    parser.add_argument("--params-b", type=float, default=DEFAULT_BASE_PARAMS_B,
                        help="모델 파라미터 수(B 단위, 기록용)")
    args = parser.parse_args(argv)

    if args.status:
        return cmd_status()
    return cmd_run(force=args.force, base_id=args.base_id, params_b=args.params_b)


if __name__ == "__main__":
    sys.exit(main())
