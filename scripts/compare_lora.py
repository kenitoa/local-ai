from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from core.optimizer_core.local_model_runtime import VllmOfflineRuntime


DEFAULT_PROMPT = "Optimize this code while preserving behavior. Return JSON with diagnosis and unified diff."


def generate(runtime: VllmOfflineRuntime, prompt: str) -> dict[str, object]:
    started = time.perf_counter()
    content = runtime.chat(
        messages=[
            {"role": "system", "content": "You are a code optimization assistant."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=900,
    )
    return {"elapsed_seconds": round(time.perf_counter() - started, 3), "content": content}


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare base vLLM output and LoRA adapter output without an HTTP server.")
    parser.add_argument("--model-path", default="/models/base/code-model")
    parser.add_argument("--lora-adapter-name", default="code-optimizer-lora")
    parser.add_argument("--lora-adapter-path", default="/models/adapters/code-optimizer-lora")
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/eval_sets/lora_comparison.json"))
    args = parser.parse_args()

    prompt = args.prompt_file.read_text(encoding="utf-8") if args.prompt_file else DEFAULT_PROMPT
    base_runtime = VllmOfflineRuntime(model_path=args.model_path)
    lora_runtime = VllmOfflineRuntime(
        model_path=args.model_path,
        lora_enabled=True,
        lora_adapter_name=args.lora_adapter_name,
        lora_adapter_path=args.lora_adapter_path,
    )
    result = {
        "prompt": prompt,
        "base": generate(base_runtime, prompt),
        "lora": generate(lora_runtime, prompt),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
