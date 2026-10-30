from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel

from ..config import Settings
from .base import LLMError, LLMUsage, StructuredMixin

log = logging.getLogger(__name__)


class OllamaProvider(StructuredMixin):
    """Provider para modelos locais via Ollama (endpoint OpenAI-compatible).

    Sem custo por token. Requer Ollama rodando: https://ollama.com
    Modelos recomendados: qwen2.5:14b, mistral-nemo, llama3.3

    Exemplo de uso:
        ollama pull qwen2.5:14b
        ABSTRATOR_LLM_PROVIDER=ollama ABSTRATOR_OLLAMA_MODEL=qwen2.5:14b uv run abstrator run "..."
    """

    def __init__(self, settings: Settings) -> None:
        self.provider_name = "ollama"
        self.model_name = settings.ollama_model or settings.llm_model
        self.temperature = settings.llm_temperature
        self.max_attempts = settings.llm_max_retries + 1
        self.pricing = (0.0, 0.0)
        self.usage_log = []
        self._settings = settings
        self._usage = LLMUsage()
        self._supports_schema_format = True
        self._client = httpx.AsyncClient(
            base_url=settings.ollama_base_url.rstrip("/"),
            timeout=settings.llm_timeout,
            headers={"Content-Type": "application/json"},
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
            "stream": False,
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
            log.info("Ollama nao suporta response_format=json_schema; usando prompt-only")
            return await self._complete(prompt, schema, system, temperature, previous_error)
        if resp.status_code >= 400:
            detail = resp.text[:500]
            if "model" in detail.lower() and "not found" in detail.lower():
                raise LLMError(
                    f"Modelo '{self.model_name}' nao encontrado no Ollama. "
                    f"Execute: ollama pull {self.model_name}"
                )
            raise LLMError(f"Ollama erro {resp.status_code}: {detail}")
        data = resp.json()
        usage = data.get("usage") or {}
        self._usage = LLMUsage(
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )
        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"Ollama: resposta sem choices: {str(data)[:400]}")
        content = (choices[0].get("message") or {}).get("content") or ""
        if not content:
            raise LLMError(f"Ollama: resposta sem conteudo: {str(choices[0])[:400]}")
        return str(content)
