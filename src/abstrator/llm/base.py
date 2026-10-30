from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class LLMError(RuntimeError):
    """Falha ao obter uma saida estruturada valida do provider."""


@dataclass(slots=True)
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 1


@dataclass(slots=True)
class LLMResult(Generic[T]):
    value: T
    usage: LLMUsage
    raw: str = ""
    model: str = ""
    provider: str = ""
    attempts: int = 1


@runtime_checkable
class LLMProvider(Protocol):
    """Toda ainteligencia do abstrator passa por aqui."""

    name: str
    model: str

    async def complete_structured(
        self,
        prompt: str,
        schema: type[T],
        *,
        system: str | None = None,
        temperature: float | None = None,
        stage: str = "",
    ) -> LLMResult[T]: ...

    async def aclose(self) -> None: ...


def json_schema_of(schema: type[BaseModel]) -> dict[str, Any]:
    return schema.model_json_schema()


def schema_instruction(schema: type[BaseModel]) -> str:
    schema_json = json.dumps(json_schema_of(schema), ensure_ascii=False, indent=2)
    return (
        "Responda EXCLUSIVAMENTE com um objeto JSON valido, sem texto antes ou depois, "
        "sem comentarios e sem blocos de markdown.\n"
        "O objeto deve conformar exatamente com este JSON Schema:\n"
        f"{schema_json}\n"
        "Regras: use apenas ids de fonte existentes na lista fornecida; "
        "se nao souber, use lista vazia em vez de inventar id; "
        "se nao souber a resposta, use string vazia ou lista vazia."
    )


def extract_json(text: str) -> str:
    """Pega o primeiro objeto JSON balanceado de uma resposta possivelmente suja."""
    text = text.strip()
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    if text.startswith("{"):
        return text
    start = text.find("{")
    if start == -1:
        raise LLMError("nenhum objeto JSON encontrado na resposta do LLM")
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise LLMError("JSON nao balanceado na resposta do LLM")


def parse_structured(
    raw: str,
    schema: type[T],
    *,
    max_attempts: int = 3,
    repair: Any = None,
) -> tuple[T, int]:
    """Valida a resposta; se falhar, tenta consertar (chamada LLM ou heuristica)."""
    last_error: Exception | None = None
    attempt = 0
    current = raw
    while attempt < max_attempts:
        attempt += 1
        try:
            return schema.model_validate_json(extract_json(current)), attempt
        except (ValidationError, LLMError, json.JSONDecodeError) as exc:
            last_error = exc
            log.warning("saida estruturada invalida (tentativa %s): %s", attempt, exc)
            if attempt >= max_attempts or repair is None:
                break
            current = repair(str(exc), current)
    raise LLMError(f"nao foi possível validar a saida contra {schema.__name__}: {last_error}")


@dataclass
class StructuredMixin:
    """Rotina comum: monta prompt, insere schema, valida e cobra retry."""

    provider_name: str = "base"
    model_name: str = ""
    temperature: float = 0.0
    max_attempts: int = 3
    pricing: tuple[float, float] = (0.0, 0.0)
    usage_log: list[LLMUsage] = field(default_factory=list)

    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        pin, pout = self.pricing
        return (input_tokens * pin + output_tokens * pout) / 1_000_000

    async def complete_structured(  # type: ignore[override]
        self,
        prompt: str,
        schema: type[T],
        *,
        system: str | None = None,
        temperature: float | None = None,
        stage: str = "",
    ) -> LLMResult[T]:
        attempts = 0
        raw = ""
        error: Exception | None = None
        for attempts in range(1, self.max_attempts + 1):
            raw = await self._complete(prompt, schema, system, temperature, error)
            try:
                value = schema.model_validate_json(extract_json(raw))
            except (ValidationError, LLMError, json.JSONDecodeError) as exc:
                error = exc
                log.warning(
                    "[%s] stage=%s tentativa %s falhou: %s",
                    self.provider_name,
                    stage,
                    attempts,
                    exc,
                )
                if attempts < self.max_attempts:
                    raw = self._repair_prompt(raw, str(exc), prompt)
                continue
            usage = self._last_usage
            usage.cost_usd = self._cost(usage.input_tokens, usage.output_tokens)
            usage.calls = attempts
            self.usage_log.append(usage)
            return LLMResult(
                value=value,
                usage=usage,
                raw=raw,
                model=self.model_name,
                provider=self.provider_name,
                attempts=attempts,
            )
        raise LLMError(f"{self.provider_name} nao devolveu JSON valido: {error}")

    def _repair_prompt(self, raw: str, error: str, original: str) -> str:
        return (
            f"{original}\n\nA tentativa anterior falhou. Erro de validacao: {error}\n"
            "Responda novamente com JSON valido no formato pedido.\n"
            f"Tentativa anterior: {raw[:2000]}"
        )

    async def _complete(
        self,
        prompt: str,
        schema: type[BaseModel],
        system: str | None,
        temperature: float | None,
        previous_error: Exception | None,
    ) -> str:
        raise NotImplementedError

    @property
    def _last_usage(self) -> LLMUsage:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


def run_with_semaphore_factory(limit: int) -> asyncio.Semaphore:
    return asyncio.Semaphore(limit)
