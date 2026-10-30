from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Context, MCPServer

from .audit import AuditLog
from .config import IdFactory, get_settings
from .engine.budget import BudgetTracker
from .engine.complexity import assess_complexity as _assess_complexity
from .engine.expand import expand_node as _expand_node
from .engine.llm_runner import LLMRunner
from .engine.orchestrator import Orchestrator
from .engine.research import ResearchEngine, SourceRegistry
from .engine.synthesize import analysis_from_findings, integrate
from .llm import build_provider
from .models import Complexity, Lens, Run
from .search.cache import Cache
from .search.fetch import Fetcher
from .search.searxng import SearxngClient
from .store import list_runs as _list_runs
from .store import load_run, resolve_run_id, save_run

log = logging.getLogger("abstrator.mcp")

# runs em andamento neste processo (para o kill switch por MCP)
ACTIVE: dict[str, Orchestrator] = {}

mcp = MCPServer(
    "abstrator",
    instructions=(
        "Pesquisa por abstracao recursiva. Fluxo recomendado: assess_complexity "
        "(barato) para decidir se vale abstract -> abstract para a run completa "
        "(JSON com arvore de nos, fontes citadas e learning_path) -> expand_node "
        "para aprofundar nos que pararam em max_depth ou budget."
    ),
)


def _lenses(names: list[str] | None) -> tuple[Lens, ...] | None:
    if not names:
        return None
    parsed = []
    for name in names:
        try:
            parsed.append(Lens(name.strip()))
        except ValueError as exc:
            available = ", ".join(lens.value for lens in Lens)
            raise ValueError(f"lente invalida: {name} (use: {available})") from exc
    return tuple(parsed)


def _make_runner(settings, on_event=None) -> tuple[BudgetTracker, LLMRunner]:
    budget = BudgetTracker.from_settings(settings, "standard")
    runner = LLMRunner(settings, build_provider(settings), budget, None, None, on_event)
    return budget, runner


@mcp.tool()
async def assess_complexity(
    concept: str,
    goal: str = "",
) -> dict[str, Any]:
    """Avalia se um conceito e simples ou precisa ser decomposto (barato, use antes de abstract)."""
    settings = get_settings()
    budget, runner = _make_runner(settings)
    complexity: Complexity = await _assess_complexity(runner, concept, goal, 0)
    await runner.provider.aclose()
    return {
        "concept": concept,
        "complexity": complexity.model_dump(mode="json"),
        "hint": (
            "vale rodar abstract()"
            if complexity.verdict.value == "complex"
            else "use research_concept() direto: um no so ja resolve"
        ),
        "usd": round(budget.usd, 6),
    }


@mcp.tool()
async def abstract(  # noqa: A001 - nome da ferramenta e o nome do plano
    ctx: Context,
    query: str,
    mode: str = "standard",
    lenses: list[str] | None = None,
    max_depth: int | None = None,
    max_fanout: int | None = None,
    max_nodes: int | None = None,
    goal_context: str = "",
) -> str:
    """Executa a cadeia de abstracao completa e devolve o JSON estruturado da run.

    Comece por assess_complexity_tool para decidir se isso compensa.
    mode: quick | standard | deep. lenses: ex.: ["meaning","practice","existing_tools"].
    """
    settings = get_settings()
    audit = AuditLog(Path(settings.runs_dir), None, enabled=True)
    cache = Cache(settings.db_path, enabled=True)

    started: dict[str, str] = {}

    async def emit(event: dict[str, Any]) -> None:
        if event.get("event") == "start":
            started["run_id"] = event.get("run_id", "")
            ACTIVE[event["run_id"]] = orchestrator
        try:
            await ctx.report_progress(float(event.get("depth", 0)), event)
        except Exception:  # cliente sem suporte a progresso
            log.info("%s", event)

    orchestrator = Orchestrator(
        settings, build_provider(settings), cache=cache, audit=audit, on_event=emit
    )
    try:
        run = await orchestrator.run(
            query,
            mode=mode,
            lenses=_lenses(lenses),
            max_depth=max_depth,
            max_fanout=max_fanout,
            max_nodes=max_nodes,
            goal_context=goal_context,
        )
    finally:
        if started.get("run_id"):
            ACTIVE.pop(started["run_id"], None)
        await orchestrator.aclose()
        cache.close()
    save_run(settings, run)
    return run.model_dump_json(indent=2)


@mcp.tool()
def cancel_run(run_id: str) -> str:
    """Kill switch: cancela uma execucao em andamento e devolve a arvore parcial depois."""
    orchestrator = ACTIVE.get(run_id)
    if orchestrator is None:
        return json.dumps(
            {"run_id": run_id, "cancelled": False, "motivo": "run nao esta em andamento"}
        )
    orchestrator.cancel()
    return json.dumps({"run_id": run_id, "cancelled": True, "motivo": "cancelamento solicitado"})


@mcp.tool()
async def research_concept(
    concept: str,
    lenses: list[str] | None = None,
    goal: str = "",
    mode: str = "standard",
) -> str:
    """Pesquisa um unico conceito pelas lentes indicadas, sem recursao. JSON de um no."""
    settings = get_settings()
    parsed = _lenses(lenses)
    if parsed is None:
        parsed = settings.mode(mode).lenses
    budget, runner = _make_runner(settings)
    registry = SourceRegistry(IdFactory(settings.node_prefix, settings.source_prefix))
    search = SearxngClient(settings, budget)
    fetcher = Fetcher(settings, budget)
    engine = ResearchEngine(settings, search, fetcher, runner, registry)
    try:
        result = await engine.research(concept, goal, parsed)
        integration = await integrate(runner, concept, goal, [], result.findings)
        analysis, confidence = analysis_from_findings(
            result.findings, integration, set(registry.sources)
        )
    finally:
        await search.aclose()
        await fetcher.aclose()
        await runner.provider.aclose()
    return json.dumps(
        {
            "concept": concept,
            "lenses": [lens.value for lens in parsed],
            "queries": result.queries,
            "analysis": analysis.model_dump(mode="json"),
            "confidence": confidence,
            "sources": {
                sid: source.model_dump(mode="json") for sid, source in registry.sources.items()
            },
            "budget": budget.snapshot().model_dump(mode="json"),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def expand_node(
    run_id: str, node_id: str, extra_depth: int = 1, mode: str = "standard"
) -> str:
    """Aprofunda um no que parou cedo (ex.: MAX_DEPTH) e salva a run atualizada."""
    settings = get_settings()
    target = resolve_run_id(settings, run_id)
    run = load_run(settings, target)
    updated = await _expand_node(settings, run, node_id, extra_depth=extra_depth, mode=mode)
    save_run(settings, updated)
    return updated.model_dump_json(indent=2)


@mcp.tool()
def get_run(run_id: str) -> str:
    """Devolve o JSON completo de uma execucao salva."""
    settings = get_settings()
    return load_run(settings, resolve_run_id(settings, run_id)).model_dump_json(indent=2)


@mcp.tool()
def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    """Lista as execucoes salvas (mais recentes primeiro)."""
    settings = get_settings()
    return [meta.model_dump(mode="json") for meta in _list_runs(settings, limit)]


@mcp.resource("abstraction://schema")
def schema_resource() -> str:
    """JSON Schema da saida do abstrator."""
    return json.dumps(Run.model_json_schema(), ensure_ascii=False, indent=2)


@mcp.resource("abstraction://runs/{run_id}")
def run_resource(run_id: str) -> str:
    """Resultado de uma execucao, como resource."""
    settings = get_settings()
    return load_run(settings, resolve_run_id(settings, run_id)).model_dump_json(indent=2)


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    mcp.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover
    main()
