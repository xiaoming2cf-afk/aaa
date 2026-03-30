from __future__ import annotations

from copy import deepcopy


_LLM_PROVIDER_SPECS: list[dict[str, str]] = [
    {
        "kind": "openai",
        "category": "llm",
        "label": "OpenAI",
        "description": "Official OpenAI API connection for GPT models.",
        "default_base_url": "",
        "default_model": "",
        "docs_url": "https://platform.openai.com/docs/overview",
        "family": "native",
    },
    {
        "kind": "deepseek",
        "category": "llm",
        "label": "DeepSeek",
        "description": "DeepSeek OpenAI-compatible chat completions endpoint.",
        "default_base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "docs_url": "https://api-docs.deepseek.com/",
        "family": "openai_compatible",
    },
    {
        "kind": "gemini",
        "category": "llm",
        "label": "Gemini",
        "description": "Google Gemini via the OpenAI-compatible Gemini API.",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.5-flash",
        "docs_url": "https://ai.google.dev/gemini-api/docs/openai",
        "family": "openai_compatible",
    },
    {
        "kind": "anthropic",
        "category": "llm",
        "label": "Anthropic",
        "description": "Anthropic Claude via the OpenAI SDK compatibility layer.",
        "default_base_url": "https://api.anthropic.com/v1/",
        "default_model": "claude-sonnet-4-0",
        "docs_url": "https://docs.anthropic.com/en/api/openai-sdk",
        "family": "openai_compatible",
    },
    {
        "kind": "kimi",
        "category": "llm",
        "label": "Kimi",
        "description": "Moonshot AI Kimi models through the Moonshot API.",
        "default_base_url": "https://api.moonshot.ai/v1",
        "default_model": "kimi-k2.5",
        "docs_url": "https://platform.moonshot.ai/docs/guide/use-kimi-k2-thinking-model.en-US",
        "family": "openai_compatible",
    },
    {
        "kind": "openai_compatible",
        "category": "llm",
        "label": "OpenAI Compatible",
        "description": "Custom OpenAI-compatible endpoint such as OpenRouter or self-hosted gateways.",
        "default_base_url": "",
        "default_model": "",
        "docs_url": "",
        "family": "openai_compatible",
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
