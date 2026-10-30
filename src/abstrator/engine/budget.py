from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..config import Settings
from ..llm.base import LLMUsage
from ..models import Budget, StopReason


class BudgetExceeded(RuntimeError):
    def __init__(self, reason: StopReason) -> None:
        super().__init__(f"orcamento excedido: {reason.value}")
        self.reason = reason


@dataclass
class BudgetTracker:
    """Contador rigido de recursos. Ao bater o limite, para com elegancia.

    `stopped_by` e informativo (por que a run parou antes da hora);
    `ensure()` so levanta quando os limites de recurso foram de fato estourados.
    """

    max_queries: int
    max_pages: int
    max_llm_calls: int
    max_tokens: int
    max_seconds: float
    max_usd: float
    queries: int = 0
    pages: int = 0
    llm_calls: int = 0
    tokens: int = 0
    seconds: float = 0.0
    usd: float = 0.0
    stopped_by: str | None = None
    cancelled: bool = False
    _start: float = field(default_factory=time.monotonic)

    @classmethod
    def from_settings(cls, settings: Settings, mode: str) -> BudgetTracker:
        limits = settings.scaled_budget(mode)
        return cls(
            max_queries=limits["max_queries"],
            max_pages=limits["max_pages"],
            max_llm_calls=limits["max_llm_calls"],
            max_tokens=limits["max_tokens"],
            max_seconds=limits["max_seconds"],
            max_usd=limits["max_usd"],
        )

    # --- verificacao ------------------------------------------------------- #

    def elapsed(self) -> float:
        return max(time.monotonic() - self._start, self.seconds)

    def resource_reason(self) -> StopReason | None:
        if self.cancelled:
            return StopReason.CANCELLED
        if (
            self.queries >= self.max_queries
            or self.pages >= self.max_pages
            or self.llm_calls >= self.max_llm_calls
            or self.tokens >= self.max_tokens
            or self.usd >= self.max_usd
            or self.elapsed() >= self.max_seconds
        ):
            return StopReason.BUDGET
        return None

    def ensure(self) -> None:
        reason = self.resource_reason()
        if reason is not None:
            self.stop(reason)
            raise BudgetExceeded(reason)

    @property
    def stopped(self) -> bool:
        return self.resource_reason() is not None

    def stop(self, reason: StopReason) -> None:
        if reason is StopReason.CANCELLED:
            self.cancelled = True
        if self.stopped_by is None:
            self.stopped_by = reason.value

    # --- consumo ---------------------------------------------------------- #

    def spend_query(self, n: int = 1) -> None:
        self.queries += n

    def spend_page(self, n: int = 1) -> None:
        self.pages += n

    def spend_llm(self, usage: LLMUsage) -> None:
        self.llm_calls += 1
        self.tokens += usage.input_tokens + usage.output_tokens
        self.usd += usage.cost_usd
        self.seconds = self.elapsed()
        reason = self.resource_reason()
        if reason is not None and self.stopped_by is None:
            self.stopped_by = reason.value

    # --- saida ------------------------------------------------------------- #

    def snapshot(self) -> Budget:
        self.seconds = self.elapsed()
        return Budget(
            max_queries=self.max_queries,
            max_pages=self.max_pages,
            max_llm_calls=self.max_llm_calls,
            max_tokens=self.max_tokens,
            max_seconds=self.max_seconds,
            max_usd=self.max_usd,
            queries=self.queries,
            pages=self.pages,
            llm_calls=self.llm_calls,
            tokens=self.tokens,
            seconds=round(self.seconds, 3),
            usd=round(self.usd, 6),
            stopped_by=self.stopped_by,
        )
