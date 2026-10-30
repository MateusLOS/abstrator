from __future__ import annotations

import pytest

from abstrator.engine.budget import BudgetExceeded, BudgetTracker
from abstrator.llm.base import LLMUsage
from abstrator.models import StopReason


def tracker(**kwargs) -> BudgetTracker:
    base = dict(
        max_queries=3,
        max_pages=4,
        max_llm_calls=5,
        max_tokens=1000,
        max_seconds=60.0,
        max_usd=1.0,
    )
    base.update(kwargs)
    return BudgetTracker(**base)


def test_limits_from_settings_are_scaled(settings):
    small = BudgetTracker.from_settings(settings, "quick")
    standard = BudgetTracker.from_settings(settings, "standard")
    deep = BudgetTracker.from_settings(settings, "deep")

    assert small.max_llm_calls < standard.max_llm_calls < deep.max_llm_calls
    assert small.max_queries == int(settings.budget_max_queries * 0.35)


def test_ensure_raises_when_limit_is_hit():
    budget = tracker()
    budget.spend_query(3)
    with pytest.raises(BudgetExceeded) as exc:
        budget.ensure()
    assert exc.value.reason is StopReason.BUDGET
    assert budget.stopped_by == "budget"
    assert budget.stopped


def test_structural_stop_reason_does_not_block_resources():
    budget = tracker()
    budget.stop(StopReason.MAX_NODES)

    budget.ensure()  # max_nodes e informacional: nao trava o restante
    assert budget.stopped_by == "max_nodes"


def test_cancel_blocks_and_is_recorded():
    budget = tracker()
    budget.stop(StopReason.CANCELLED)

    assert budget.cancelled
    with pytest.raises(BudgetExceeded) as exc:
        budget.ensure()
    assert exc.value.reason is StopReason.CANCELLED


def test_llm_spending_tracks_tokens_and_cost():
    budget = tracker()
    budget.spend_llm(LLMUsage(input_tokens=100, output_tokens=50, cost_usd=0.02))

    assert budget.llm_calls == 1
    assert budget.tokens == 150
    assert budget.usd == pytest.approx(0.02)


def test_usd_limit_stops_the_run():
    budget = tracker(max_usd=0.05)
    budget.spend_llm(LLMUsage(input_tokens=1, output_tokens=1, cost_usd=0.06))

    assert budget.stopped
    assert budget.stopped_by == "budget"


def test_snapshot_reports_usage_and_limits():
    budget = tracker()
    budget.spend_page(2)
    snapshot = budget.snapshot()

    assert snapshot.pages == 2
    assert snapshot.max_pages == 4
    assert snapshot.seconds >= 0
    assert snapshot.stopped_by is None
