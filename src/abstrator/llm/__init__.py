from __future__ import annotations

from ..config import Settings
from .base import LLMError, LLMProvider, LLMResult, LLMUsage
from .fake import FakeLLM

__all__ = [
    "LLMProvider",
    "LLMResult",
    "LLMUsage",
    "LLMError",
    "FakeLLM",
    "build_provider",
]


def build_provider(settings: Settings) -> LLMProvider:
    """Instancia o provider configurado (auto resolve por disponibilidade)."""
    provider = settings.resolved_provider()
    if provider == "fake":
        return FakeLLM()
    if provider == "gemini_cli":
        from .gemini_cli import GeminiCLIProvider

        return GeminiCLIProvider(settings)
    if provider == "opencode_zen":
        from .opencode_zen import OpenCodeZenProvider

        return OpenCodeZenProvider(settings)
    if provider == "anthropic":
        from .anthropic_direct import AnthropicProvider

        return AnthropicProvider(settings)
    if provider == "ollama":
        from .ollama import OllamaProvider

        return OllamaProvider(settings)
    if provider == "openrouter":
        from .openrouter import OpenRouterProvider

        return OpenRouterProvider(settings)
    raise LLMError(f"provider desconhecido: {provider}")
