"""local-ai 자체 LoRA fine-tune 실행기.

이 스크립트는 backend 의 ``POST /api/v1/training/run`` 가 백그라운드로 spawn 한다.
독립 CLI 로도 실행 가능.

원칙
----
- **외부 모델 다운로드 금지**. 베이스는 ``models/local/base/<safe-id>/`` 에 이미
  존재해야 한다 (콜드스타트 부트스트랩 책임).
- 학습 데이터는 backend 가 ``--data`` 로 넘겨준 jsonl 파일을 그대로 읽는다.
- 결과는 ``models/local/runs/<run_name>/`` 에 LoRA 어댑터로 저장.
- DB ``llm_training_runs`` 행을 직접 업데이트한다(--run-id 가 있을 때).
- 의존성(transformers/peft/torch) 미설치 시에도 깔끔히 실패 처리.

사용
----
    python scripts/finetune_run.py \
        --base-id Qwen/Qwen2.5-Coder-1.5B \
        --data data/llm_training/runs/<run>.jsonl \
        --out  models/local/runs/<run> \
        --method lora --rank 16 --epochs 1 --batch 1 --grad-accum 8 \
        --seq-len 1024 --precision bf16 --device auto \
        --run-id 7
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# DB (선택적)
# ---------------------------------------------------------------------------
def _db_connect():
    """backend 와 동일한 환경변수로 mysql 접속. 실패 시 None."""
    try:
        import pymysql  # type: ignore
    except ImportError:
        return None
    try:
        return pymysql.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "localai"),
            password=os.getenv("DB_PASSWORD", "localai"),
            database=os.getenv("DB_NAME", "localai_db"),
            charset="utf8mb4",
            autocommit=True,
        )
    except Exception:  # noqa: BLE001
        return None


def _update_run(run_id: int | None, fields: dict[str, Any]) -> None:
    if not run_id:
        return
    conn = _db_connect()
    if conn is None:
        return
    try:
        cols = []
        vals: list[Any] = []
        for k, v in fields.items():
            cols.append(f"{k}=%s")
            if isinstance(v, (dict, list)):
                vals.append(json.dumps(v, ensure_ascii=False))
            else:
                vals.append(v)
        vals.append(run_id)
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE llm_training_runs SET {', '.join(cols)} WHERE id=%s",
                vals,
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 데이터셋
# ---------------------------------------------------------------------------
def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fp:
        for ln in fp:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue
    return out


def _format_example(ex: dict[str, Any]) -> str:
    """학습 데이터 (model_answers + reuse) 를 model-server 의 _build_prompt 와
    동일한 형식의 단일 텍스트로 변환."""
    task = (ex.get("task") or "generate").strip()
    lang = ex.get("language") or "plain"
    lib = ex.get("library") or "-"
    req = (ex.get("requirement") or "").strip()
    in_code = (ex.get("input_code") or "").strip()
    out_code = (ex.get("output_code") or "").strip()
    explanation = (ex.get("explanation") or "").strip()

    header = f"### Task: {task}\n### Language: {lang}\n### Library: {lib}\n"
    if task in ("spec_to_code", "generate"):
        body = f"### Requirement:\n{req}\n\n### Output (code only):\n{out_code}"
    elif task == "optimize":
        body = (
            f"### Requirement:\n{req}\n\n"
            f"### Input code:\n{in_code}\n\n"
            f"### Optimized code:\n{out_code}"
        )
    elif task == "explain":
        body = f"### Code:\n{in_code}\n\n### Explanation:\n{explanation}"
    else:
        body = f"### Input:\n{req or in_code}\n\n### Output:\n{out_code or explanation}"
    return header + body


# ---------------------------------------------------------------------------
# 학습
# ---------------------------------------------------------------------------
def _safe_name(model_id: str) -> str:
    return model_id.replace("/", "__").replace(":", "_")


def _resolve_base_dir(base_id: str) -> Path:
    candidate = REPO_ROOT / "models" / "local" / "base" / _safe_name(base_id)
    if not (candidate / "config.json").is_file():
        raise SystemExit(
            f"cold-start base not found: {candidate}\n"
            "→ run scripts/bootstrap_cold_start.py first."
        )
    return candidate


def run_training(args: argparse.Namespace) -> dict[str, Any]:
    log = logging.getLogger("finetune")

    base_dir = _resolve_base_dir(args.base_id)
    data_path = Path(args.data).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    samples = _load_jsonl(data_path)
    if not samples:
        raise SystemExit(f"empty training data: {data_path}")

    log.info("base=%s  samples=%d  out=%s  method=%s",
             base_dir, len(samples), out_dir, args.method)

    # 무거운 의존성은 여기서 import (실패 시 메시지 명확)
    try:
        import torch  # type: ignore
        from datasets import Dataset  # type: ignore
        from transformers import (  # type: ignore
            AutoModelForCausalLM, AutoTokenizer,
            DataCollatorForLanguageModeling,
            Trainer, TrainingArguments,
        )
    except ImportError as exc:
        raise SystemExit(
            f"missing dependency: {exc}\n"
            "→ pip install transformers peft accelerate datasets torch"
        ) from exc

    # 오프라인 강제: snapshot_download 가 도는 일이 없게.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    # device / dtype
    if args.device == "cuda" and torch.cuda.is_available():
        device = "cuda"
    elif args.device == "cpu":
        device = "cpu"
    else:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    if args.precision == "bf16" and device == "cuda" and torch.cuda.is_bf16_supported():
        dtype = torch.bfloat16
    elif args.precision == "fp16" and device == "cuda":
        dtype = torch.float16
    else:
        dtype = torch.float32

    # tokenizer + base
    tokenizer = AutoTokenizer.from_pretrained(
        str(base_dir), local_files_only=True, trust_remote_code=False,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        str(base_dir),
        local_files_only=True,
        trust_remote_code=False,
        torch_dtype=dtype,
    )

    # LoRA 적용 (method=lora|qlora 일 때)
    if args.method in ("lora", "qlora"):
        try:
            from peft import LoraConfig, get_peft_model  # type: ignore
        except ImportError as exc:
            raise SystemExit(f"peft not installed: {exc}") from exc
        peft_cfg = LoraConfig(
            r=args.rank,
            lora_alpha=args.alpha,
            lora_dropout=args.dropout,
            bias="none",
            task_type="CAUSAL_LM",
        )
        model = get_peft_model(model, peft_cfg)
        model.print_trainable_parameters()
    elif args.method == "full":
        pass  # 모든 파라미터 학습
    else:
        raise SystemExit(f"unknown method: {args.method}")

    # 데이터셋 토크나이즈
    texts = [_format_example(e) for e in samples]

    def _tok(batch: dict[str, list[str]]) -> dict[str, Any]:
        enc = tokenizer(
            batch["text"],
            truncation=True,
            max_length=args.seq_len,
            padding=False,
        )
        enc["labels"] = [list(ids) for ids in enc["input_ids"]]
        return enc

    ds = Dataset.from_dict({"text": texts}).map(
        _tok, batched=True, remove_columns=["text"]
    )
    collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    training_args = TrainingArguments(
        output_dir=str(out_dir / "_trainer"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        bf16=(dtype == torch.bfloat16),
        fp16=(dtype == torch.float16),
        logging_steps=10,
        save_strategy="no",
        report_to=[],
        optim=args.optimizer,
        gradient_checkpointing=args.grad_ckpt,
        remove_unused_columns=False,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=ds,
        data_collator=collator,
    )

    started = datetime.utcnow()
    train_result = trainer.train()
    finished = datetime.utcnow()

    # 어댑터/전체 저장
    model.save_pretrained(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))

    metrics = {
        "train_loss":      float(train_result.training_loss),
        "train_runtime_s": float(train_result.metrics.get("train_runtime", 0.0)),
        "samples":         len(samples),
        "epochs":          args.epochs,
        "batch":           args.batch,
        "grad_accum":      args.grad_accum,
        "seq_len":         args.seq_len,
        "method":          args.method,
        "device":          device,
        "dtype":           str(dtype).replace("torch.", ""),
    }

    summary = {
        "status":          "done",
        "checkpoint_path": str(out_dir.relative_to(REPO_ROOT)),
        "metrics":         metrics,
        "started_at":      started.isoformat() + "Z",
        "finished_at":     finished.isoformat() + "Z",
    }
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="local-ai LoRA fine-tune runner")
    p.add_argument("--base-id", required=True)
    p.add_argument("--data",    required=True, help="jsonl path")
    p.add_argument("--out",     required=True, help="output checkpoint dir")
    p.add_argument("--run-id",  type=int, default=0, help="llm_training_runs.id (DB update 대상)")

    p.add_argument("--method",     default="lora", choices=["full", "lora", "qlora"])
    p.add_argument("--rank",       type=int, default=16)
    p.add_argument("--alpha",      type=int, default=32)
    p.add_argument("--dropout",    type=float, default=0.05)
    p.add_argument("--epochs",     type=int, default=1)
    p.add_argument("--batch",      type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--seq-len",    type=int, default=1024)
    p.add_argument("--lr",         type=float, default=2e-4)
    p.add_argument("--precision",  default="bf16", choices=["bf16", "fp16", "fp32"])
    p.add_argument("--device",     default="auto", choices=["auto", "cpu", "cuda"])
    p.add_argument("--optimizer",  default="adamw_torch")
    p.add_argument("--grad-ckpt",  action="store_true")
    return p.parse_args()


def main() -> int:
    args = _parse()

    log_path = LOG_DIR / f"finetune_{args.run_id or 'cli'}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()],
    )
    log = logging.getLogger("finetune")

    _update_run(args.run_id, {
        "status":        "running",
        "started_at":    datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "log_file_path": str(log_path.relative_to(REPO_ROOT)),
    })

    try:
        summary = run_training(args)
    except SystemExit as exc:
        log.error("aborted: %s", exc)
        _update_run(args.run_id, {
            "status":      "failed",
            "finished_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "metrics_json": {"error": str(exc)},
        })
        return 2
    except Exception as exc:  # noqa: BLE001
        log.error("training crashed: %s\n%s", exc, traceback.format_exc())
        _update_run(args.run_id, {
            "status":       "failed",
            "finished_at":  datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "metrics_json": {"error": str(exc), "trace": traceback.format_exc()[-2000:]},
        })
        return 1

    _update_run(args.run_id, {
        "status":          "done",
        "finished_at":     datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "metrics_json":    summary["metrics"],
        "checkpoint_path": summary["checkpoint_path"],
    })
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
