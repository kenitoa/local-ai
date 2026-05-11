from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = str(ROOT_DIR / "data")


@dataclass(frozen=True, slots=True)
class OptimizerConfig:
    ai_device: str = "cpu"
    llm_backend: str = "llama_cpp"
    model_backend: str = "cpu"
    model_path: str = "/models"
    llm_model: str = "local-code-model"
    llama_cpp_model_path: str = "/models/gguf/code-model-q4.gguf"
    llama_cpp_n_ctx: int = 8192
    llama_cpp_n_threads: int = 8
    llama_cpp_n_gpu_layers: int = 0
    vllm_model_path: str = "/models/base/code-model"
    vllm_tensor_parallel_size: int = 1
    base_model_path: str = "/models/base/code-model"
    lora_enabled: bool = False
    lora_adapter_name: str = "code-optimizer-lora"
    lora_adapter_path: str = "/models/adapters/code-optimizer-lora"
    data_dir: str = DEFAULT_DATA_DIR
    embedding_backend: str = "sentence_transformers"
    embedding_model_path: str = "/models/embeddings/code-search"
    embedding_dimension: int = 384


@lru_cache
def get_config() -> OptimizerConfig:
    return OptimizerConfig(
        ai_device=env("AI_DEVICE", "cpu"),
        llm_backend=env("LLM_BACKEND", "llama_cpp"),
        model_backend=env("MODEL_BACKEND", "cpu"),
        model_path=env("MODEL_PATH", "/models"),
        llm_model=env("LLM_MODEL", "local-code-model"),
        llama_cpp_model_path=env("LLAMA_CPP_MODEL_PATH", "/models/gguf/code-model-q4.gguf"),
        llama_cpp_n_ctx=env_int("LLAMA_CPP_N_CTX", 8192),
        llama_cpp_n_threads=env_int("LLAMA_CPP_N_THREADS", 8),
        llama_cpp_n_gpu_layers=env_int("LLAMA_CPP_N_GPU_LAYERS", 0),
        vllm_model_path=env("VLLM_MODEL_PATH", env("BASE_MODEL_PATH", "/models/base/code-model")),
        vllm_tensor_parallel_size=env_int("VLLM_TENSOR_PARALLEL_SIZE", 1),
        base_model_path=env("BASE_MODEL_PATH", "/models/base/code-model"),
        lora_enabled=env_bool("LORA_ENABLED", False),
        lora_adapter_name=env("LORA_ADAPTER_NAME", "code-optimizer-lora"),
        lora_adapter_path=env("LORA_ADAPTER_PATH", "/models/adapters/code-optimizer-lora"),
        data_dir=env("DATA_DIR", DEFAULT_DATA_DIR),
        embedding_backend=env("EMBEDDING_BACKEND", "sentence_transformers"),
        embedding_model_path=env("EMBEDDING_MODEL_PATH", "/models/embeddings/code-search"),
        embedding_dimension=env_int("EMBEDDING_DIMENSION", 384),
    )


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


config = get_config()
