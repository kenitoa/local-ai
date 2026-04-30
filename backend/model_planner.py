"""local-ai backend: 자체 학습형(A안) 모델 예산 계산기.

### 설계 의도
이 프로젝트는 **외부 사전학습 모델을 다운로드해서 그대로 쓰는 방식이 아니라**,
처음 한 번 *콜드스타트용 베이스 1개*만 받아오고 그 이후로는 **사용자 데이터로
계속 fine-tune** 해서 자기 모델을 만든다. 본 모듈은 모델을 "선택" 하지 않는다.
대신 현재 기기 사양에서:

1. 어떤 학습 방식이 가능한가?  (full / lora / qlora / disabled)
2. 한 번에 올릴 수 있는 batch / seq_len 은 얼마인가?
3. 옵티마이저 상태까지 포함한 학습 메모리 예산은?
4. 학습된 자기 가중치를 추론할 때 쓰는 컨텍스트/스레드는?

를 **결정론적**으로 계산해서 dict 로 반환한다. 외부 모델 카탈로그를 두지
않으므로 보안 정책(외부 다운로드 금지)을 위반할 여지가 없다.

### 콜드스타트 베이스
유일하게 허용되는 외부 다운로드는 ``COLD_START_BASE`` 단 한 항목이다.
``BOOTSTRAP_ALLOW_DOWNLOAD`` 가 True 이고 ``models/local/<fingerprint>/``
밑에 가중치가 아직 없을 때만 1회 받는다. 그 이후 모든 추가 학습은 자기
체크포인트 위에서 이루어진다.
"""
from __future__ import annotations

import os
from typing import Any

# ---------------------------------------------------------------------------
# 콜드스타트 베이스 (유일한 외부 모델, 1회만 다운로드)
# ---------------------------------------------------------------------------
# 사용자가 .env 의 COLD_START_BASE_ID 로 덮어쓸 수 있다.
# 기본값은 ~1B 파라미터급 코드 친화 오픈소스 (Apache-2.0).
COLD_START_BASE: dict[str, Any] = {
    "id":        os.getenv("COLD_START_BASE_ID", "Qwen/Qwen2.5-Coder-1.5B"),
    "params_b":  float(os.getenv("COLD_START_BASE_PARAMS_B", "1.5")),
    "license":   "Apache-2.0",
    "purpose":   "초기 가중치 1회 다운로드. 이후 모든 학습은 자체 fine-tune.",
}

# 보안 정책: 외부 다운로드는 콜드스타트 1회만 허용.
EXTERNAL_DOWNLOAD_POLICY: dict[str, Any] = {
    "allow_cold_start_only": True,
    "allow_other_downloads": False,
    "rationale": "로컬/온프레미스 보안 환경. 콜드스타트 외 외부 모델/데이터 다운로드 금지.",
}


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _device_from_profile(profile: dict[str, Any]) -> str:
    if (profile.get("run_mode") or "").lower() == "gpu":
        if profile.get("cuda_available"):
            return "cuda"
        if profile.get("directml_available"):
            return "directml"
        return "gpu"
    if (profile.get("accelerator") or "").lower() == "mps":
        return "mps"
    return "cpu"


def _safe_thread_count(cores: int | None) -> int:
    c = int(cores or 0)
    if c <= 0:
        return 2
    if c <= 2:
        return c
    if c <= 4:
        return c - 1
    return max(2, c - 2)


# ---------------------------------------------------------------------------
# 학습 예산 (training budget) — 1.5B 베이스 기준
#
# VRAM 대략 추정 (1.5B, seq_len=2048, AdamW):
#   - full bf16/fp16          : ~22 GB  (가중치 3 + 그래드 3 + 옵티 16)
#   - LoRA fp16 (rank 16)     : ~8  GB
#   - QLoRA 4bit (rank 16)    : ~5  GB
#   - CPU full bf16           : RAM ~24 GB
#   - CPU LoRA bf16           : RAM ~10 GB
# ---------------------------------------------------------------------------
def plan_training(profile: dict[str, Any]) -> dict[str, Any]:
    device = _device_from_profile(profile)
    cores = int(profile.get("cpu_cores") or 0)
    threads = _safe_thread_count(cores)

    if device in ("cuda", "directml", "gpu"):
        vram_mb = int(profile.get("gpu_vram_mb") or 0)
        precision = "bf16" if device == "cuda" else "fp16"

        if vram_mb >= 24000:
            method, per_dev_bs, grad_accum, seq_len = "full", 4, 8, 2048
            grad_ckpt, optimizer = False, "adamw_torch"
        elif vram_mb >= 16000:
            method, per_dev_bs, grad_accum, seq_len = "full", 2, 16, 2048
            grad_ckpt, optimizer = True, "adamw_torch"
        elif vram_mb >= 10000:
            method, per_dev_bs, grad_accum, seq_len = "lora", 4, 8, 2048
            grad_ckpt, optimizer = True, "adamw_torch"
        elif vram_mb >= 6000:
            method, per_dev_bs, grad_accum, seq_len = "lora", 2, 16, 1024
            grad_ckpt, optimizer = True, "adamw_8bit"
        else:
            method, per_dev_bs, grad_accum, seq_len = "qlora", 1, 32, 1024
            grad_ckpt, optimizer = True, "paged_adamw_8bit"

    else:
        ram_mb = int(profile.get("ram_mb") or 0)
        precision = "bf16"
        if ram_mb >= 32000:
            method, per_dev_bs, grad_accum, seq_len = "lora", 2, 16, 1024
            grad_ckpt, optimizer = True, "adamw_torch"
        elif ram_mb >= 16000:
            method, per_dev_bs, grad_accum, seq_len = "lora", 1, 32, 512
            grad_ckpt, optimizer = True, "adamw_torch"
        elif ram_mb >= 8000:
            method, per_dev_bs, grad_accum, seq_len = "qlora", 1, 32, 512
            grad_ckpt, optimizer = True, "adamw_8bit"
        else:
            return {
                "trainable":     False,
                "device":        "cpu",
                "method":        "disabled",
                "reason":        f"insufficient RAM ({ram_mb} MB) for fine-tuning",
                "n_threads":     threads,
            }

    eff_batch = per_dev_bs * grad_accum
    return {
        "trainable":              True,
        "device":                 device,
        "precision":              precision,
        "method":                 method,            # full | lora | qlora | disabled
        "lora_rank":              16 if method in ("lora", "qlora") else 0,
        "lora_alpha":             32 if method in ("lora", "qlora") else 0,
        "lora_dropout":           0.05 if method in ("lora", "qlora") else 0.0,
        "per_device_batch_size":  per_dev_bs,
        "grad_accum_steps":       grad_accum,
        "effective_batch_size":   eff_batch,
        "seq_len":                seq_len,
        "gradient_checkpointing": grad_ckpt,
        "optimizer":              optimizer,
        "n_threads":              threads,
        "max_params_b":           COLD_START_BASE["params_b"],
    }


# ---------------------------------------------------------------------------
# 추론 예산 (자기 학습 가중치를 굴릴 때)
# ---------------------------------------------------------------------------
def plan_inference(profile: dict[str, Any]) -> dict[str, Any]:
    device = _device_from_profile(profile)
    cores = int(profile.get("cpu_cores") or 0)
    threads = _safe_thread_count(cores)

    if device in ("cuda", "directml", "gpu"):
        vram_mb = int(profile.get("gpu_vram_mb") or 0)
        if vram_mb >= 16000:
            n_ctx, n_batch, n_gpu_layers = 16384, 512, 32
        elif vram_mb >= 8000:
            n_ctx, n_batch, n_gpu_layers = 8192, 256, 32
        elif vram_mb >= 4000:
            n_ctx, n_batch, n_gpu_layers = 4096, 128, 24
        else:
            n_ctx, n_batch, n_gpu_layers = 2048, 64, 0
        return {
            "device":          device,
            "n_ctx":           n_ctx,
            "n_batch":         n_batch,
            "n_threads":       threads,
            "n_gpu_layers":    n_gpu_layers,
            "max_concurrency": 2,
        }

    ram_mb = int(profile.get("ram_mb") or 0)
    if ram_mb >= 16000:
        n_ctx, n_batch = 8192, 128
    elif ram_mb >= 8000:
        n_ctx, n_batch = 4096, 64
    else:
        n_ctx, n_batch = 2048, 32
    return {
        "device":          "cpu",
        "n_ctx":           n_ctx,
        "n_batch":         n_batch,
        "n_threads":       threads,
        "n_gpu_layers":    0,
        "max_concurrency": 1,
    }


# ---------------------------------------------------------------------------
# 단일 진입점
# ---------------------------------------------------------------------------
def plan_all(profile: dict[str, Any]) -> dict[str, Any]:
    if not profile:
        raise ValueError("hardware profile is empty")
    train = plan_training(profile)
    infer = plan_inference(profile)

    if train.get("trainable"):
        summary = (
            f"device={infer['device']} · train={train['method']}"
            f"({train['precision']}, eff_batch={train['effective_batch_size']}, "
            f"seq_len={train['seq_len']}) · "
            f"infer ctx={infer['n_ctx']}, gpu_layers={infer['n_gpu_layers']}"
        )
    else:
        summary = (
            f"device={infer['device']} · train=disabled (insufficient resources) · "
            f"infer ctx={infer['n_ctx']}"
        )

    return {
        "schema_version": 2,                # 1=외부모델 선택형(폐기), 2=자체학습 예산형
        "summary":        summary,
        "bootstrap":      {
            **COLD_START_BASE,
            "policy": EXTERNAL_DOWNLOAD_POLICY,
        },
        "train":          train,
        "infer":          infer,
        "source": {
            "profile_id":   profile.get("id"),
            "fingerprint":  profile.get("fingerprint"),
            "run_mode":     profile.get("run_mode"),
            "accelerator":  profile.get("accelerator"),
            "cpu_cores":    profile.get("cpu_cores"),
            "ram_mb":       profile.get("ram_mb"),
            "gpu_model":    profile.get("gpu_model"),
            "gpu_vram_mb":  profile.get("gpu_vram_mb"),
        },
    }
