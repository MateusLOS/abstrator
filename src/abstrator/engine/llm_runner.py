from __future__ import annotations

import logging
from typing import Any, TypeVar

from pydantic import BaseModel

from ..audit import AuditLog
from ..config import Settings
from ..llm.base import LLMProvider
from ..search.cache import Cache
from .budget import BudgetTracker

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMRunner:
    """Camada fina entre o engine e o LLM: cache, budget, auditoria, eventos."""

    def __init__(
        self,
        settings: Settings,
        provider: LLMProvider,
        budget: BudgetTracker,
        cache: Cache | None = None,
        audit: AuditLog | None = None,
        on_event: Any | None = None,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.budget = budget
        self.cache = cache
        self.audit = audit
        self.on_event = on_event
        self.total_usd = 0.0

    async def run(
        self,
        schema: type[T],
        *,
        stage: str,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        use_cache: bool = True,
    ) -> T:
        self.budget.ensure()
        if self.cache is not None and use_cache:
            cached = await self.cache.get_llm(
                prompt, schema.__name__, self.settings.cache_ttl_hours
            )
            if cached is not None:
                self._audit("llm_cache_hit", stage=stage, schema=schema.__name__)
                return schema.model_validate(cached)

        result = await self.provider.complete_structured(
            prompt, schema, system=system, temperature=temperature, stage=stage
        )
        self.budget.spend_llm(result.usage)
        self.total_usd += result.usage.cost_usd
        self._audit(
            "llm",
            stage=stage,
            schema=schema.__name__,
            model=result.model,
            provider=result.provider,
            in_tokens=result.usage.input_tokens,
            out_tokens=result.usage.output_tokens,
            usd=round(result.usage.cost_usd, 6),
            attempts=result.attempts,
        )
        self._event({"event": "llm", "stage": stage, "usd": round(result.usage.cost_usd, 6)})
        if self.cache is not None and use_cache:
            await self.cache.put_llm(prompt, schema.__name__, result.value.model_dump(mode="json"))
        return result.value

    def _audit(self, event: str, **fields: Any) -> None:
        if self.audit is not None:
            self.audit.record(event, **fields)

    def _event(self, payload: dict[str, Any]) -> None:
        if self.on_event is not None:
            try:
                self.on_event(payload)
            except Exception:  # pragma: no cover - callback do consumidor
                log.exception("falha no callback de progresso")
