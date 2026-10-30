"""Call the ask tool directly."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from abstrator.audit import AuditLog
from abstrator.config import get_settings
from abstrator.engine.orchestrator import Orchestrator
from abstrator.llm import build_provider
from abstrator.models import Run
from abstrator.search.cache import Cache
from abstrator.store import save_run


def _format_response(run: Run) -> str:
    lines: list[str] = []
    if run.summary:
        lines.append(run.summary)
        lines.append("")
    if run.recommendations:
        lines.append("## Recomendações")
        lines.append("")
        for rec in run.recommendations:
            lines.append(f"- {rec.text}")
            if rec.rationale:
                lines.append(f"  _{rec.rationale}_")
        lines.append("")
    root = run.nodes.get(run.root_id)
    if root and root.analysis.open_questions:
        lines.append("## Questões em aberto")
        lines.append("")
        for q in root.analysis.open_questions:
            lines.append(f"- {q}")
        lines.append("")
    n_sources = len(run.sources)
    footer_parts = []
    if n_sources:
        footer_parts.append(f"{n_sources} fonte{'s' if n_sources != 1 else ''} consultada{'s' if n_sources != 1 else ''}")
    if run.budget.seconds:
        footer_parts.append(f"{run.budget.seconds:.0f}s")
    if run.budget.usd:
        footer_parts.append(f"${run.budget.usd:.4f}")
    if run.budget.stopped_by:
        footer_parts.append(f"parou por {run.budget.stopped_by}")
    if footer_parts:
        lines.append(f"---\n*{' · '.join(footer_parts)}*")
    return "\n".join(lines).strip()


async def main():
    settings = get_settings()
    audit = AuditLog(Path(settings.runs_dir), None, enabled=False)
    cache = Cache(settings.db_path, enabled=True)

    orchestrator = Orchestrator(
        settings, build_provider(settings), cache=cache, audit=audit, on_event=None
    )
    run_id = ""
    try:
        run = await orchestrator.run("como fazer design", mode="quick", goal_context="")
        run_id = run.run_id
    finally:
        await orchestrator.aclose()
        cache.close()

    save_run(settings, run)
    print(_format_response(run))


if __name__ == "__main__":
    asyncio.run(main())
