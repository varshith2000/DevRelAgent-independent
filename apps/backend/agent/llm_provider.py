"""
LLM Provider Abstraction — Multi-provider support

Supports Anthropic (default), OpenAI, and Google Gemini.
Select provider via LLM_PROVIDER env var.

Usage:
    from agent.llm_provider import get_llm, llm_generate
    
    llm = get_llm()
    response = llm_generate("Explain this code", max_tokens=1000)
"""

import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")

# Supported Gemini models (free and paid)
GEMINI_MODELS = [
    "gemini-2.5",           # Latest Gemini 2.5 (recommended)
    "gemini-2.0-flash-exp", # Gemini 2.0 Flash Experimental
    "gemini-1.5-pro",       # Gemini 1.5 Pro
    "gemini-1.5-flash",     # Gemini 1.5 Flash
    "gemini-1.5-flash-8b"   # Gemini 1.5 Flash 8B (lightweight)
]


class LLMProvider:
    """Abstract LLM provider interface."""

    def __init__(self, model: str):
        self.model = model

    def generate(self, prompt: str, max_tokens: int = 1000, system: Optional[str] = None) -> str:
        raise NotImplementedError


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""

    def __init__(self, model: str):
        super().__init__(model)
        from anthropic import Anthropic
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    def generate(self, prompt: str, max_tokens: int = 1000, system: Optional[str] = None) -> str:
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        response = self.client.messages.create(**kwargs)
        return response.content[0].text.strip()


class OpenAIProvider(LLMProvider):
    """OpenAI GPT provider."""

    def __init__(self, model: str):
        super().__init__(model)
        from openai import OpenAI
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def generate(self, prompt: str, max_tokens: int = 1000, system: Optional[str] = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=messages,
        )
        return response.choices[0].message.content.strip()


class GeminiProvider(LLMProvider):
    """Google Gemini provider."""

    def __init__(self, model: str):
        super().__init__(model)
        from google import genai
        self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

    def generate(self, prompt: str, max_tokens: int = 1000, system: Optional[str] = None) -> str:
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        response = self.client.models.generate_content(
            model=self.model,
            contents=full_prompt,
            config={"max_output_tokens": max_tokens},
        )
        return response.text.strip()


# ─── Factory ─────────────────────────────────────────

_PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}

_instance: Optional[LLMProvider] = None


def get_llm(provider: Optional[str] = None, model: Optional[str] = None) -> LLMProvider:
    """Get or create the singleton LLM provider."""
    global _instance
    p = provider or LLM_PROVIDER
    m = model or LLM_MODEL
    if _instance is None or (provider and provider != LLM_PROVIDER):
        cls = _PROVIDERS.get(p)
        if cls is None:
            raise ValueError(f"Unknown LLM provider: {p}. Choose from: {list(_PROVIDERS.keys())}")
        _instance = cls(m)
    return _instance


def llm_generate(prompt: str, max_tokens: int = 1000, system: Optional[str] = None) -> str:
    """Convenience: generate text using the configured LLM provider."""
    return get_llm().generate(prompt, max_tokens=max_tokens, system=system)
