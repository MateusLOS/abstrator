from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel

from ..config import Settings
from .base import LLMError, LLMUsage, StructuredMixin

log = logging.getLogger(__name__)


class OpenRouterProvider(StructuredMixin):
    """Provider para OpenRouter: acesso a centenas de modelos via uma API unificada.

    https://openrouter.ai — requer OPENROUTER_API_KEY.
    Util para alternar entre modelos especializados sem gerenciar multiplas contas:
    DeepSeek para raciocinio, Qwen para textos tecnicos, Llama para uso intensivo.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.openrouter_api_key:
            raise LLMError(
                "OPENROUTER_API_KEY nao configurada. Crie uma chave em "
                "https://openrouter.ai/keys e adicione ao .env"
            )
        self.provider_name = "openrouter"
        self.model_name = settings.llm_model
        self.temperature = settings.llm_temperature
        self.max_attempts = settings.llm_max_retries + 1
        self.pricing = settings.pricing()
        self.usage_log = []
        self._settings = settings
        self._usage = LLMUsage()
        self._supports_schema_format = True
        self._client = httpx.AsyncClient(
            base_url=settings.openrouter_base_url.rstrip("/"),
            timeout=settings.llm_timeout,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/local/abstrator",
                "X-Title": "abstrator",
            },
        )

    @property
    def _last_usage(self) -> LLMUsage:
        return self._usage

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _complete(
        self,
        prompt: str,
        schema: type[BaseModel],
        system: str | None,
        temperature: float | None,
        previous_error: Exception | None,
    ) -> str:
        body: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "user", "content": f"{system}\n\n{prompt}" if system else prompt}
            ],
            "temperature": (self._settings.llm_temperature if temperature is None else temperature),
            "max_tokens": self._settings.llm_max_output_tokens,
        }
        if self._supports_schema_format:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                    "strict": False,
                },
            }
        resp = await self._client.post("/chat/completions", json=body)
        if resp.status_code == 400 and self._supports_schema_format:
            self._supports_schema_format = False
            log.info("OpenRouter recusou response_format=json_schema; usando prompt-only")
            return await self._complete(prompt, schema, system, temperature, previous_error)
        if resp.status_code == 429:
            raise LLMError("rate limit (429) no OpenRouter")
        if resp.status_code >= 400:
            raise LLMError(f"OpenRouter erro {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        usage = data.get("usage") or {}
        self._usage = LLMUsage(
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )
        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"OpenRouter: resposta sem choices: {str(data)[:400]}")
        content = (choices[0].get("message") or {}).get("content") or ""
        if not content:
            raise LLMError(f"OpenRouter: resposta sem conteudo: {str(choices[0])[:400]}")
        return str(content)
