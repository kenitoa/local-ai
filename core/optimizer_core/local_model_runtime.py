from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.optimizer_core.config import OptimizerConfig, config


class LocalModelRuntime(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs: object) -> str:
        raise NotImplementedError

    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        return self.generate(render_chat_prompt(messages), **kwargs)

    @property
    @abstractmethod
    def backend_name(self) -> str:
        raise NotImplementedError


class LlamaCppRuntime(LocalModelRuntime):
    def __init__(
        self,
        model_path: str,
        device: str = "cpu",
        n_ctx: int = 8192,
        n_threads: int = 8,
        n_gpu_layers: int = 0,
    ) -> None:
        self.model_path = model_path
        self.device = device
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self.n_gpu_layers = n_gpu_layers if device == "cuda" else 0
        self._llm: Any | None = None

    @property
    def backend_name(self) -> str:
        return "llama_cpp"

    def generate(self, prompt: str, **kwargs: object) -> str:
        result = self._model().create_completion(
            prompt=prompt,
            temperature=float(kwargs.get("temperature", 0.2)),
            max_tokens=int(kwargs.get("max_tokens", 1024)),
        )
        return str(result["choices"][0]["text"])

    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        result = self._model().create_chat_completion(
            messages=messages,
            temperature=float(kwargs.get("temperature", 0.2)),
            max_tokens=int(kwargs.get("max_tokens", 1024)),
        )
        return str(result["choices"][0]["message"]["content"])

    def _model(self) -> Any:
        if self._llm is not None:
            return self._llm
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise RuntimeError(
                "llama-cpp-python is not installed. Install CPU requirements or use deterministic mode."
            ) from exc

        self._llm = Llama(
            model_path=self.model_path,
            n_ctx=self.n_ctx,
            n_threads=self.n_threads,
            n_gpu_layers=self.n_gpu_layers,
            verbose=False,
        )
        return self._llm


class VllmOfflineRuntime(LocalModelRuntime):
    def __init__(
        self,
        model_path: str,
        tensor_parallel_size: int = 1,
        lora_enabled: bool = False,
        lora_adapter_name: str = "code-optimizer-lora",
        lora_adapter_path: str = "/models/adapters/code-optimizer-lora",
    ) -> None:
        self.model_path = model_path
        self.tensor_parallel_size = tensor_parallel_size
        self.lora_enabled = lora_enabled
        self.lora_adapter_name = lora_adapter_name
        self.lora_adapter_path = lora_adapter_path
        self._llm: Any | None = None

    @property
    def backend_name(self) -> str:
        return "vllm_offline"

    def generate(self, prompt: str, **kwargs: object) -> str:
        from vllm import SamplingParams

        params = SamplingParams(
            temperature=float(kwargs.get("temperature", 0.2)),
            max_tokens=int(kwargs.get("max_tokens", 1024)),
        )
        generate_kwargs: dict[str, Any] = {}
        lora_request = self._lora_request()
        if lora_request is not None:
            generate_kwargs["lora_request"] = lora_request
        outputs = self._model().generate([prompt], params, **generate_kwargs)
        return str(outputs[0].outputs[0].text)

    def _model(self) -> Any:
        if self._llm is not None:
            return self._llm
        try:
            from vllm import LLM
        except ImportError as exc:
            raise RuntimeError("vLLM is not installed. Use a CUDA runtime image or deterministic mode.") from exc

        self._llm = LLM(
            model=self.model_path,
            tensor_parallel_size=self.tensor_parallel_size,
            enable_lora=self.lora_enabled,
        )
        return self._llm

    def _lora_request(self) -> Any | None:
        if not self.lora_enabled:
            return None
        try:
            from vllm.lora.request import LoRARequest
        except ImportError as exc:
            raise RuntimeError("vLLM LoRA support is unavailable in this runtime.") from exc
        return LoRARequest(self.lora_adapter_name, 1, self.lora_adapter_path)


class TransformersRuntime(LocalModelRuntime):
    def __init__(self, model_path: str, device: str = "cpu") -> None:
        self.model_path = model_path
        self.device = device
        self._tokenizer: Any | None = None
        self._model_instance: Any | None = None

    @property
    def backend_name(self) -> str:
        return "transformers"

    def generate(self, prompt: str, **kwargs: object) -> str:
        tokenizer, model = self._load()
        inputs = tokenizer(prompt, return_tensors="pt")
        if self.device == "cuda":
            inputs = {key: value.to("cuda") for key, value in inputs.items()}
        output_ids = model.generate(
            **inputs,
            do_sample=float(kwargs.get("temperature", 0.2)) > 0,
            temperature=float(kwargs.get("temperature", 0.2)),
            max_new_tokens=int(kwargs.get("max_tokens", 1024)),
        )
        prompt_length = inputs["input_ids"].shape[-1]
        generated = output_ids[0][prompt_length:]
        return str(tokenizer.decode(generated, skip_special_tokens=True))

    def _load(self) -> tuple[Any, Any]:
        if self._tokenizer is not None and self._model_instance is not None:
            return self._tokenizer, self._model_instance
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("transformers is not installed. Install CUDA/Transformers requirements.") from exc

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_path)
        self._model_instance = AutoModelForCausalLM.from_pretrained(self.model_path)
        if self.device == "cuda":
            self._model_instance = self._model_instance.to("cuda")
        return self._tokenizer, self._model_instance


def get_local_model_runtime(app_config: OptimizerConfig = config) -> LocalModelRuntime:
    backend = app_config.llm_backend.lower()
    if backend == "vllm":
        return VllmOfflineRuntime(
            model_path=app_config.vllm_model_path,
            tensor_parallel_size=app_config.vllm_tensor_parallel_size,
            lora_enabled=app_config.lora_enabled,
            lora_adapter_name=app_config.lora_adapter_name,
            lora_adapter_path=app_config.lora_adapter_path,
        )

    if backend == "llama_cpp":
        return LlamaCppRuntime(
            model_path=app_config.llama_cpp_model_path,
            device=app_config.ai_device,
            n_ctx=app_config.llama_cpp_n_ctx,
            n_threads=app_config.llama_cpp_n_threads,
            n_gpu_layers=app_config.llama_cpp_n_gpu_layers,
        )

    if backend == "transformers":
        return TransformersRuntime(model_path=app_config.base_model_path, device=app_config.ai_device)

    raise ValueError(f"Unsupported local model runtime: {app_config.llm_backend}")


def render_chat_prompt(messages: list[dict[str, str]]) -> str:
    rendered = []
    for message in messages:
        role = message.get("role", "user").strip() or "user"
        content = message.get("content", "")
        rendered.append(f"{role.upper()}:\n{content}")
    rendered.append("ASSISTANT:\n")
    return "\n\n".join(rendered)
