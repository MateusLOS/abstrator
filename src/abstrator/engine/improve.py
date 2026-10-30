from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from ..config import Settings
from ..llm import build_provider
from ..models import Improvements, Run
from ..prompts import render
from .budget import BudgetTracker
from .llm_runner import LLMRunner
from .orchestrator import Orchestrator

SELF_GOAL = (
    "melhorar a ferramenta abstrator: uma CLI + servidor MCP que decompoe um pedido por "
    "abstracao recursiva, pesquisa cada conceito por lentes com fontes citadas e devolve "
    "JSON estruturado, com budget rigido, guardrails (robots.txt, rate limit, sem cookies), "
    "memoizacao e auditoria"
)


def snapshot_facts(settings: Settings) -> dict[str, str]:
    """Auto-introspeccao barata: fatos que a LLM nao tem como saber sozinha."""
    root = Path(settings.runs_dir)
    facts: dict[str, str] = {
        "modo padrao": settings.llm_provider,
        "modelo": settings.llm_model,
        "max_depth standard": str(settings.mode("standard").max_depth),
        "fanout standard": str(settings.mode("standard").max_fanout),
        "orcamento standard": (
            f"{settings.budget_max_llm_calls} chamadas LLM, "
            f"{settings.budget_max_queries} buscas, {settings.budget_max_pages} paginas, "
            f"{settings.budget_max_seconds}s"
        ),
        "cache de conceitos (h)": str(settings.concept_cache_ttl_hours),
        "runs gravados": str(len(list(root.iterdir())) if root.exists() else 0),
    }
    return facts


def self_assessment(run: Run) -> str:
    paths = ", ".join(
        f"{node_id}({node.status.value},conf={node.confidence:.2f},fontes={len(run.sources)})"
        for node_id, node in list(run.nodes.items())[:12]
    )
    return (
        f"{run.summary}\n\nnos: {paths}\n"
        f"consultas: {run.budget.queries}, paginas: {run.budget.pages}"
    )


async def improve(
    settings: Settings,
    *,
    mode: str = "quick",
    max_depth: int = 2,
) -> tuple[Improvements, Path, Run]:
    """Meta-modo: abstrai o proprio objetivo do projeto e grava propostas em docs/.

    Nao altera codigo. Um humano revisa e aplica.
    """
    orchestrator = Orchestrator(settings, build_provider(settings))
    run = await orchestrator.run(SELF_GOAL, mode=mode, max_depth=max_depth)
    await orchestrator.aclose()

    facts = "\n".join(f"- {k}: {v}" for k, v in snapshot_facts(settings).items())
    prompt = render(
        "improve",
        goal=SELF_GOAL,
        summary=f"{self_assessment(run)}\n\nconfiguracao atual:\n{facts}",
    )
    runner = LLMRunner(
        settings,
        build_provider(settings),
        BudgetTracker.from_settings(settings, mode),
        cache=None,
        audit=None,
    )
    improvements: Improvements = await runner.run(Improvements, stage="improve", prompt=prompt)
    await runner.provider.aclose()

    directory = Path(settings.runs_dir).parent / "docs" / "improvements"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{dt.date.today().isoformat()}-{run.run_id}.md"
    path.write_text(_render(improvements, run, facts), encoding="utf-8")
    return improvements, path, run


def _render(improvements: Improvements, run: Run, facts: str) -> str:
    lines = [
        f"# Melhorias proposals para o abstrator ({run.run_id})",
        "",
        "Gerado pelo meta-modo `abstrator improve`. **Nada foi alterado no codigo.**",
        "",
        "## Auto-abstracao do objetivo",
        "",
        run.summary,
        "",
        f"- run da auto-analise: `{run.run_id}`",
        f"- nos: {len(run.nodes)} | fontes: {len(run.sources)} | consultas: {run.budget.queries}",
        "",
        "## Configuracao observada",
        "",
        facts,
        "",
        "## Propostas",
        "",
    ]
    if not improvements.proposals:
        lines.append("_Nenhuma proposta gerada._")
    for i, proposal in enumerate(improvements.proposals, start=1):
        lines += [
            f"### {i}. {proposal.title}",
            "",
            f"- **problema**: {proposal.problem}",
            f"- **proposta**: {proposal.proposal}",
            f"- **impacto**: {proposal.impact} | **esforco**: {proposal.effort}",
            f"- **por que**: {proposal.rationale}",
            "",
        ]
    return "\n".join(lines)


def strip_markdown(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
