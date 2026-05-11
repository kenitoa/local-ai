# Models

Store local model files here through a Docker volume or a host bind mount.

Recommended split:

- `base/code-model/` for the GPU vLLM base coder model.
- `adapters/code-optimizer-lora/` for the LoRA adapter.
- `gguf/code-model-q4.gguf` for direct CPU inference through `llama-cpp-python`.
- `embeddings/code-search/` for the local code search embedding model used by `sentence-transformers`.
- `cache/` for tokenizer and runtime cache files.

Expected layout:

```text
/models/
|-- base/
|   `-- code-model/
|-- adapters/
|   `-- code-optimizer-lora/
|-- embeddings/
|   `-- code-search/
`-- gguf/
    `-- code-model-q4.gguf
```

Do not commit downloaded model binaries.
