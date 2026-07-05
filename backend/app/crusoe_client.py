from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

BASE_URL = "https://api.inference.crusoecloud.com/v1/"

MODEL_MAP = {
    "deepseek": "deepseek-ai/Deepseek-V4-Flash",
    "nemotron_ultra": "nvidia/NVIDIA-Nemotron-3-Ultra-550B",
    "gemma": "google/gemma-4-31b-it",
    "nemotron_omni": "nvidia/Nemotron-3-Nano-Omni-Reasoning-30B-A3B",
    "kimi": "moonshotai/Kimi-K2.6",
}

REASONING_MODELS = {"deepseek", "nemotron_ultra", "nemotron_omni", "kimi"}

_DISABLE_THINKING_BODY = {
    "deepseek": {"chat_template_kwargs": {"thinking": False}},
    "kimi": {"chat_template_kwargs": {"thinking": False}},
    "nemotron_ultra": {"chat_template_kwargs": {"enable_thinking": False}},
    "nemotron_omni": {"chat_template_kwargs": {"enable_thinking": False}},
}


def crusoe_configured() -> bool:
    return bool(os.getenv("CRUSOE_API_KEY"))


def mock_mode() -> bool:
    value = os.getenv("MOCK_CRUSOE", "true").strip().lower()
    return value in {"1", "true", "yes", "on"} or not crusoe_configured()


def get_llm(
    model_key: str,
    structured: bool = False,
    disable_thinking: bool = False,
) -> ChatOpenAI:
    model_id = MODEL_MAP.get(model_key, MODEL_MAP["nemotron_ultra"])
    api_key = os.getenv("CRUSOE_API_KEY")
    if not api_key:
        raise RuntimeError("CRUSOE_API_KEY is not configured")

    kwargs: dict = {
        "model": model_id,
        "base_url": BASE_URL,
        "api_key": api_key,
    }
    if model_key in REASONING_MODELS and (structured or disable_thinking):
        kwargs["temperature"] = 0.2
        kwargs["max_tokens"] = 2048
        kwargs["extra_body"] = _DISABLE_THINKING_BODY[model_key]
    else:
        kwargs["temperature"] = 0.6
        kwargs["top_p"] = 0.95
    return ChatOpenAI(**kwargs)
