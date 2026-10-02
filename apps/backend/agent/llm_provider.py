"""
LLM Provider Abstraction — Multi-provider support

Supports Anthropic (default), OpenAI, Google Gemini, and z.ai GLM.
Select provider via LLM_PROVIDER env var.

Usage:
    from agent.llm_provider import get_llm, llm_generate

    llm = get_llm()
    response = llm_generate("Explain this code", max_tokens=1000)
"""

import logging
from typing import Optional

from config.settings import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()
LLM_PROVIDER = _settings.llm_provider.lower()
LLM_MODEL = _settings.llm_model

# Supported Gemini models (free and paid)
GEMINI_MODELS = [
    "gemini-2.5",           # Latest Gemini 2.5 (recommended)
    "gemini-2.0-flash-exp", # Gemini 2.0 Flash Experimental
    "gemini-1.5-pro",       # Gemini 1.5 Pro
    "gemini-1.5-flash",     # Gemini 1.5 Flash
    "gemini-1.5-flash-8b"   # Gemini 1.5 Flash 8B (lightweight)
]

# Supported z.ai GLM models
ZAI_MODELS = [
    "glm-4-plus",           # GLM-4 Plus (most capable)
    "glm-4-air",            # GLM-4 Air (balanced performance)
    "glm-4-flash",          # GLM-4 Flash (fastest, cost-effective)
    "glm-4-long",           # GLM-4 Long (extended context)
    "glm-zero",             # GLM-Zero (reasoning-optimized)
    "glm-4.5-air",          # GLM-4.5 Air (newer version)
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
        self.client = Anthropic(api_key=get_settings().anthropic_api_key)

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
        self.client = OpenAI(api_key=get_settings().openai_api_key)

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
        self.client = genai.Client(api_key=get_settings().google_api_key)
        # Ensure model name has the correct prefix for the GenAI SDK
        if not model.startswith("models/"):
            self.model = f"models/{model}"

    def generate(self, prompt: str, max_tokens: int = 1000, system: Optional[str] = None) -> str:
        full_prompt = f"{system}\n\n{prompt}" if system else prompt

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config={"max_output_tokens": max_tokens},
            )

            # Handle response safely - check if text exists
            if response and hasattr(response, 'text') and response.text:
                return response.text.strip()
            elif response and hasattr(response, 'candidates') and response.candidates:
                # Fallback to candidates if text is not available
                if response.candidates[0].content.parts:
                    return response.candidates[0].content.parts[0].text.strip()
            # If all else fails, return empty string
            logger.warning(f"Gemini response had no text content. Response type: {type(response)}, hasattr text: {hasattr(response, 'text')}")
            return ""

        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ""


class ZAIProvider(LLMProvider):
    """z.ai GLM provider (Zhipu AI)."""

    def __init__(self, model: str):
        super().__init__(model)
        from openai import OpenAI
        # Zhipu AI uses OpenAI-compatible API with JWT authentication
        # The API key format should be: id.secret
        api_key = get_settings().z_ai_api_key
        # Validate API key format
        if not api_key or "." not in api_key:
            raise ValueError("Z_AI_API_KEY must be in format: id.secret (e.g., 12345678.abcdef)")
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://open.bigmodel.cn/api/paas/v4/"
        )

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


# ─── Factory ─────────────────────────────────────────

_PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "zai": ZAIProvider,
    "glm": ZAIProvider,  # Alias for zai
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
