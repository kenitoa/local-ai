from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def default_root_dir() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists() and (parent / "core").exists():
            return parent
    return Path.cwd()


ROOT_DIR = default_root_dir()
DEFAULT_DATA_DIR = str(ROOT_DIR / "data")


class Settings(BaseSettings):
    app_name: str = "AI Code Optimizer"
    app_env: str = "local"
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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
