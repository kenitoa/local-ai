from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT_DIR / "data" / "fine_tune" / "splits" / "train.jsonl"
DEFAULT_OUTPUT = ROOT_DIR / "checkpoints" / "code-optimizer-lora"


def load_hf_token() -> str | None:
    token_path = os.getenv("HF_TOKEN_PATH", "/run/secrets/hf_token")
    path = Path(token_path)
    if not path.exists():
        return None
    token = path.read_text(encoding="utf-8").strip()
    if token:
        os.environ["HF_TOKEN"] = token
        os.environ["HUGGING_FACE_HUB_TOKEN"] = token
        return token
    return None


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    records: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    if not records:
        raise ValueError(f"Dataset is empty: {path}")
    return records


def require_cuda() -> None:
    ai_device = os.getenv("AI_DEVICE", "cpu").lower()
    if ai_device != "cuda":
        raise SystemExit("LoRA/QLoRA training is disabled outside the CUDA profile. Collect data on CPU instead.")


def validate_messages(records: list[dict[str, object]]) -> None:
    for index, record in enumerate(records, start=1):
        messages = record.get("messages")
        if not isinstance(messages, list) or len(messages) < 2:
            raise ValueError(f"Record {index} has invalid messages.")
        for message in messages:
            if not isinstance(message, dict) or not message.get("role") or not message.get("content"):
                raise ValueError(f"Record {index} has invalid message payload.")


def render_chat(messages: list[dict[str, str]]) -> str:
    return "\n".join(f"<|{message['role']}|>\n{message['content']}" for message in messages) + "\n<|end|>"


def dry_run(dataset: Path) -> dict[str, object]:
    records = read_jsonl(dataset)
    validate_messages(records)
    sample = records[0]
    rendered = render_chat(sample["messages"])  # type: ignore[arg-type]
    return {
        "dataset": str(dataset),
        "records": len(records),
        "first_quality": sample.get("metadata", {}).get("quality") if isinstance(sample.get("metadata"), dict) else None,
        "first_rendered_chars": len(rendered),
    }


def train(args: argparse.Namespace) -> dict[str, object]:
    require_cuda()
    load_hf_token()
    records = read_jsonl(args.dataset)
    validate_messages(records)

    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            DataCollatorForLanguageModeling,
            Trainer,
            TrainingArguments,
        )
    except ImportError as exc:
        raise SystemExit(f"Training dependencies are missing in this environment: {exc}") from exc

    if not torch.cuda.is_available():
        raise SystemExit("CUDA is not available to PyTorch. Check NVIDIA Container Toolkit and compose.cuda.yaml.")

    rng = random.Random(args.seed)
    rng.shuffle(records)
    if args.smoke:
        records = records[: min(len(records), 8)]

    texts = [render_chat(record["messages"]) for record in records]  # type: ignore[arg-type]
    dataset = Dataset.from_dict({"text": texts})

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quantization_config = None
    if args.qlora:
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        trust_remote_code=True,
        quantization_config=quantization_config,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
    if args.qlora:
        model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=args.rank,
        lora_alpha=args.alpha,
        lora_dropout=args.dropout,
        task_type=TaskType.CAUSAL_LM,
        target_modules=args.target_modules.split(","),
    )
    model = get_peft_model(model, lora_config)

    def tokenize(batch):
        return tokenizer(
            batch["text"],
            truncation=True,
            max_length=args.max_length,
            padding=False,
        )

    tokenized = dataset.map(tokenize, batched=True, remove_columns=["text"])
    training_args = TrainingArguments(
        output_dir=str(args.output),
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.learning_rate,
        num_train_epochs=args.epochs,
        max_steps=args.max_steps if args.max_steps > 0 else -1,
        logging_steps=1 if args.smoke else 10,
        save_steps=10 if args.smoke else 100,
        bf16=True,
        report_to=[],
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
    )
    trainer.train()
    model.save_pretrained(args.output)
    tokenizer.save_pretrained(args.output)
    return {
        "output": str(args.output),
        "records": len(records),
        "base_model": args.base_model,
        "qlora": args.qlora,
        "smoke": args.smoke,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a LoRA/QLoRA adapter for code optimization.")
    parser.add_argument("--base-model", default=os.getenv("BASE_MODEL", "/models/base/code-model"))
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--qlora", action="store_true", default=os.getenv("QLORA", "1") == "1")
    parser.add_argument("--smoke", action="store_true", help="Run a tiny smoke training pass.")
    parser.add_argument("--dry-run", action="store_true", help="Validate dataset without loading model libraries.")
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--alpha", type=int, default=32)
    parser.add_argument("--dropout", type=float, default=0.05)
    parser.add_argument("--target-modules", default="q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj")
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--max-steps", type=int, default=-1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    result = dry_run(args.dataset) if args.dry_run else train(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
