from __future__ import annotations

from copy import deepcopy


_LOCAL_PROVIDER_KINDS = {
    "ollama",
    "lmstudio",
    "vllm",
    "local_openai_compatible",
}


_LLM_PROVIDER_SPECS: list[dict[str, str]] = [
    {
        "kind": "ollama",
        "category": "llm",
        "label": "Ollama",
        "description": "Local Ollama server via the OpenAI-compatible /v1 interface.",
        "default_base_url": "http://127.0.0.1:11434/v1",
        "default_model": "qwen2.5:7b-instruct",
        "docs_url": "https://github.com/ollama/ollama/blob/main/docs/openai.md",
        "family": "self_hosted",
    },
    {
        "kind": "lmstudio",
        "category": "llm",
        "label": "LM Studio",
        "description": "Local LM Studio server using its OpenAI-compatible API.",
        "default_base_url": "http://127.0.0.1:1234/v1",
        "default_model": "local-model",
        "docs_url": "https://lmstudio.ai/docs/app/api/endpoints/openai",
        "family": "self_hosted",
    },
    {
        "kind": "vllm",
        "category": "llm",
        "label": "vLLM",
        "description": "Self-hosted vLLM OpenAI-compatible inference server.",
        "default_base_url": "http://127.0.0.1:8010/v1",
        "default_model": "Qwen/Qwen2.5-3B-Instruct",
        "docs_url": "https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html",
        "family": "self_hosted",
    },
    {
        "kind": "local_openai_compatible",
        "category": "llm",
        "label": "Local OpenAI-Compatible",
        "description": "Any self-hosted OpenAI-compatible gateway running on your own infrastructure.",
        "default_base_url": "http://127.0.0.1:8010/v1",
        "default_model": "local-model",
        "docs_url": "",
        "family": "self_hosted",
    },
]


_DATA_SOURCE_PROVIDER_SPECS: list[dict[str, str]] = [
    {
        "kind": "fred",
        "category": "data_source",
        "label": "FRED",
        "description": "Federal Reserve Economic Data API for macroeconomic series.",
        "default_base_url": "",
        "default_model": "",
        "docs_url": "https://fred.stlouisfed.org/docs/api/fred/",
        "family": "official_data",
    }
]


def get_provider_catalog(default_openai_model: str) -> dict[str, list[dict[str, str]]]:
    llm = deepcopy(_LLM_PROVIDER_SPECS)
    for item in llm:
        if item["kind"] == "openai":
            item["default_model"] = default_openai_model
    return {
        "llm": llm,
        "data_source": deepcopy(_DATA_SOURCE_PROVIDER_SPECS),
    }


def get_provider_spec(kind: str, default_openai_model: str) -> dict[str, str] | None:
    normalized = (kind or "").strip()
    for group in get_provider_catalog(default_openai_model).values():
        for item in group:
            if item["kind"] == normalized:
                return item
    return None


def is_local_provider_kind(kind: str) -> bool:
    return (kind or "").strip() in _LOCAL_PROVIDER_KINDS


def apply_provider_defaults(
    *,
    kind: str,
    base_url: str,
    model: str,
    default_openai_model: str,
) -> tuple[str, str, dict[str, str] | None]:
    spec = get_provider_spec(kind, default_openai_model)
    resolved_base_url = (base_url or "").strip()
    resolved_model = (model or "").strip()
    if spec:
        if not resolved_base_url:
            resolved_base_url = spec.get("default_base_url", "").strip()
        if not resolved_model:
            resolved_model = spec.get("default_model", "").strip()
    return resolved_base_url, resolved_model, spec
