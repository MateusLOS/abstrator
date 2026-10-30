"""Script to call assess_complexity and abstract tools directly."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from abstrator.config import get_settings
from abstrator.engine.budget import BudgetTracker
from abstrator.engine.complexity import assess_complexity as _assess_complexity
from abstrator.engine.llm_runner import LLMRunner
from abstrator.engine.orchestrator import Orchestrator
from abstrator.llm import build_provider
from abstrator.search.cache import Cache
from abstrator.audit import AuditLog


def _make_runner(settings):
    budget = BudgetTracker.from_settings(settings, "standard")
    runner = LLMRunner(settings, build_provider(settings), budget, None, None, None)
    return budget, runner


class FakeContext:
    async def report_progress(self, value, data=None):
        pass


async def main():
    settings = get_settings()

    # --- 1. assess_complexity ---
    print("=== assess_complexity(concept='Bobotie') ===", flush=True)
    budget, runner = _make_runner(settings)
    from abstrator.models import Complexity
    complexity = await _assess_complexity(runner, "Bobotie", "", 0)
    await runner.provider.aclose()

    assess_result = {
        "concept": "Bobotie",
        "complexity": complexity.model_dump(mode="json"),
        "hint": (
            "vale rodar abstract()"
            if complexity.verdict.value == "complex"
            else "use research_concept() direto: um no so ja resolve"
        ),
        "usd": round(budget.usd, 6),
    }
    print(json.dumps(assess_result, indent=2, ensure_ascii=False))

    # --- 2. abstract ---
    print("\n=== abstract(query='Bobotie', mode='quick') ===", flush=True)
    audit = AuditLog(Path(settings.runs_dir), None, enabled=True)
    cache = Cache(settings.db_path, enabled=True)
    ctx = FakeContext()

    orchestrator = Orchestrator(settings, build_provider(settings), cache=cache, audit=audit, on_event=None)
    try:
        run = await orchestrator.run(
            "Bobotie",
            mode="quick",
            lenses=None,
            max_depth=None,
            max_fanout=None,
            max_nodes=None,
            goal_context="",
        )
    finally:
        await orchestrator.aclose()
        cache.close()

    from abstrator.store import save_run
    save_run(settings, run)
    abstract_json = run.model_dump_json(indent=2)
    print(abstract_json)


if __name__ == "__main__":
    asyncio.run(main())
