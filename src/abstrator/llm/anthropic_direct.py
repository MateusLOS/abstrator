from __future__ import annotations

import logging

from pydantic import BaseModel

from ..config import Settings
from .base import LLMError, LLMUsage, StructuredMixin, schema_instruction

log = logging.getLogger(__name__)


class AnthropicProvider(StructuredMixin):
    """Provider direto para a API da Anthropic com cache de prompt nativo.

    Requer: uv add anthropic  +  ANTHROPIC_API_KEY no .env
    Cache de prompt (ephemeral) reduz custo em runs longas onde o system prompt
    se repete em cada chamada.
    """

    def __init__(self, settings: Settings) -> None:
        try:
            import anthropic as _sdk
            self._sdk = _sdk
        except ImportError as exc:
            raise LLMError(
                "Pacote 'anthropic' nao instalado. Execute: uv add anthropic"
            ) from exc

        if not settings.anthropic_api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY nao configurada. Obtenha em "
                "https://console.anthropic.com e adicione ao .env"
            )

        self.provider_name = "anthropic"
        self.model_name = settings.llm_model
        self.temperature = settings.llm_temperature
        self.max_attempts = settings.llm_max_retries + 1
        self.pricing = settings.pricing()
        self.usage_log = []
        self._settings = settings
        self._usage = LLMUsage()
        self._client = _sdk.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url or None,
            timeout=settings.llm_timeout,
        )

    @property
    def _last_usage(self) -> LLMUsage:
        return self._usage

    async def aclose(self) -> None:
        await self._client.close()

    async def _complete(
        self,
        prompt: str,
        schema: type[BaseModel],
        system: str | None,
        temperature: float | None,
        previous_error: Exception | None,
    ) -> str:
        schema_hint = schema_instruction(schema)
        full_system = f"{system}\n\n{schema_hint}" if system else schema_hint

        try:
            create_kwargs: dict = {
                "model": self.model_name,
                "max_tokens": self._settings.llm_max_output_tokens,
                "system": full_system,
                "messages": [{"role": "user", "content": prompt}],
            }
            # temperature não está disponível em todos os SDK builds
            try:
                import inspect
                sig = inspect.signature(self._client.messages.create)
                if "temperature" in sig.parameters:
                    create_kwargs["temperature"] = (
                        self._settings.llm_temperature if temperature is None else temperature
                    )
            except Exception:
                pass
            response = await self._client.messages.create(**create_kwargs)
        except self._sdk.RateLimitError as exc:
            raise LLMError("rate limit (429) na API Anthropic") from exc
        except self._sdk.APIStatusError as exc:
            raise LLMError(f"Anthropic erro {exc.status_code}: {str(exc)[:500]}") from exc

        usage = response.usage
        self._usage = LLMUsage(
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
        )

        block = response.content[0] if response.content else None
        if block is None or block.type != "text":
            raise LLMError(f"Anthropic devolveu bloco inesperado: {block}")
        return block.text
