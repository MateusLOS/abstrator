from __future__ import annotations

import asyncio
import signal
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .audit import AuditLog
from .config import get_settings, reset_settings_cache
from .doctor import doctor as run_doctor
from .doctor import format_checks
from .engine.expand import expand_node
from .engine.improve import improve as run_improve
from .engine.orchestrator import Orchestrator
from .llm import build_provider
from .models import Lens
from .render.markdown import render_markdown
from .schema import export_schema
from .search.cache import Cache
from .store import list_runs, load_run, resolve_run_id, save_run

app = typer.Typer(add_completion=False, help="Abstrator: pesquisa por abstracao recursiva.")
console = Console()


def _lenses(value: str | None) -> tuple[Lens, ...] | None:
    if not value:
        return None
    names = [v.strip() for v in value.split(",") if v.strip()]
    try:
        return tuple(Lens(n) for n in names)
    except ValueError as exc:
        raise typer.BadParameter(f"lentes invalidas: {', '.join(n.value for n in Lens)}") from exc


def _progress(verbose: bool):
    if not verbose:
        return None

    def emit(event: dict) -> None:
        kind = event.get("event")
        if kind == "node_start":
            console.print(
                f"[dim]{'  ' * event['depth']}[/][cyan]explorando[/] {event['concept']}"
                f"[dim] ({event['depth']})[/]"
            )
        elif kind == "node_done":
            console.print(
                f"[dim]{'  ' * event['depth']}[/][green]ok[/] {event['concept']}"
                f" [dim]{event['status']} conf={event.get('confidence', 0):.2f}[/]"
            )
        elif kind == "node_stopped":
            console.print(f"[yellow]parado:[/] {event['concept']} ({event['reason']})")
        elif kind == "node_memo":
            console.print(f"[magenta]memo[/] {event['node_id']} <- {event['from']}")
        elif kind == "llm":
            console.print(f"[dim]llm {event['stage']} ${event['usd']:.4f}[/]")

    return emit


async def _execute(
    query: str,
    mode: str,
    lenses: tuple[Lens, ...] | None,
    max_depth: int | None,
    max_fanout: int | None,
    max_nodes: int | None,
    goal_context: str,
    verbose: bool,
    use_cache: bool,
):
    settings = get_settings()
    audit = AuditLog(Path(settings.runs_dir), None, enabled=True)
    cache = Cache(settings.db_path, enabled=use_cache)
    provider = build_provider(settings)
    orchestrator = Orchestrator(
        settings, provider, cache=cache, audit=audit, on_event=_progress(verbose)
    )
    # Ctrl+C vira cancelamento: a run fecha e devolve a arvore parcial
    previous = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, lambda *_: orchestrator.cancel())
    try:
        run = await orchestrator.run(
            query,
            mode=mode,
            lenses=lenses,
            max_depth=max_depth,
            max_fanout=max_fanout,
            max_nodes=max_nodes,
            goal_context=goal_context,
        )
    finally:
        signal.signal(signal.SIGINT, previous)
        await orchestrator.aclose()
        cache.close()
    return settings, run


@app.command()
def run(
    query: str = typer.Argument(..., help="O que voce quer pesquisa (pratico ou teorico)."),
    mode: str = typer.Option("standard", "--mode", "-m", help="quick | standard | deep"),
    fmt: str = typer.Option("md", "--format", "-f", help="json | md"),
    lenses: str | None = typer.Option(
        None, "--lenses", help="lista de lentes separada por virgula"
    ),
    max_depth: int | None = typer.Option(None, "--max-depth"),
    max_fanout: int | None = typer.Option(None, "--max-fanout"),
    max_nodes: int | None = typer.Option(None, "--max-nodes"),
    goal_context: str = typer.Option("", "--goal-context", "-g"),
    no_cache: bool = typer.Option(False, "--no-cache"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    out: Path | None = typer.Option(None, "--out", help="salvar o resultado neste arquivo"),
) -> None:
    """Executa a cadeia de abstracao e salva a run."""
    settings, result = asyncio.run(
        _execute(
            query,
            mode,
            _lenses(lenses),
            max_depth,
            max_fanout,
            max_nodes,
            goal_context,
            verbose,
            not no_cache,
        )
    )
    save_run(settings, result)
    payload = result.model_dump_json(indent=2) if fmt == "json" else render_markdown(result)
    if out:
        out.write_text(payload, encoding="utf-8")
        console.print(f"[green]salvo em[/] {out}")
    else:
        print(payload)
    console.print(
        f"[dim]run {result.run_id}: {len(result.nodes)} nos, {len(result.sources)} fontes, "
        f"{result.budget.llm_calls} chamadas LLM, {result.budget.seconds:.1f}s, "
        f"${result.budget.usd:.4f}[/]"
    )


@app.command()
def expand(
    run_id: str = typer.Argument(..., help="run_id ou prefixo"),
    node: str = typer.Argument(..., help="node_id a aprofundar (ex.: n3)"),
    extra_depth: int = typer.Option(1, "--extra-depth", "-d"),
    mode: str = typer.Option("standard", "--mode", "-m"),
    fmt: str = typer.Option("md", "--format", "-f"),
) -> None:
    """Aprofunda um no que parou cedo (MAX_DEPTH, budget, etc)."""
    settings = get_settings()
    target = resolve_run_id(settings, run_id)
    current = load_run(settings, target)
    updated = asyncio.run(
        expand_node(
            settings,
            current,
            node,
            extra_depth=extra_depth,
            mode=mode,
            on_event=_progress(True),
        )
    )
    save_run(settings, updated)
    print(render_markdown(updated) if fmt == "md" else updated.model_dump_json(indent=2))


@app.command()
def runs(limit: int = typer.Option(20, "--limit", "-n")) -> None:
    """Lista as execucoes salvas."""
    settings = get_settings()
    metas = list_runs(settings, limit)
    if not metas:
        console.print("nenhuma run salva ainda")
        return
    table = Table("run_id", "modo", "nos", "fontes", "parou por", "query")
    for meta in metas:
        table.add_row(
            meta.run_id,
            meta.mode.value if hasattr(meta.mode, "value") else str(meta.mode),
            str(meta.nodes),
            str(meta.sources),
            meta.stopped_by or "-",
            meta.query[:60],
        )
    console.print(table)


@app.command()
def get(run_id: str = typer.Argument(...), fmt: str = typer.Option("md", "--format", "-f")) -> None:
    """Mostra uma run salva."""
    settings = get_settings()
    result = load_run(settings, resolve_run_id(settings, run_id))
    print(render_markdown(result) if fmt == "md" else result.model_dump_json(indent=2))


@app.command()
def improve(
    mode: str = typer.Option("quick", "--mode", "-m"),
    max_depth: int = typer.Option(2, "--max-depth"),
) -> None:
    """Meta-modo: usa a ferramenta para melhorar a ferramenta (nao altera codigo)."""
    settings = get_settings()
    improvements, path, result = asyncio.run(run_improve(settings, mode=mode, max_depth=max_depth))
    console.print(f"[green]propostas salvas em[/] {path}")
    for proposal in improvements.proposals:
        console.print(f"- [cyan]{proposal.title}[/]: {proposal.proposal}")


@app.command()
def eval(
    queries: Path | None = typer.Option(None, "--queries", help="JSON com as queries"),
    only: str | None = typer.Option(None, "--only", help="roda so um id (q01)"),
    out: Path | None = typer.Option(None, "--out", help="salva o resultado em JSON"),
) -> None:
    """Roda o conjunto de avaliacao e mostra a rubrica de qualidade."""
    import datetime as dt

    from .audit import AuditLog
    from .engine.orchestrator import Orchestrator
    from .evaluation import evaluate, load_queries

    settings = get_settings()
    casos = [
        c for c in load_queries(str(queries) if queries else None) if not only or c["id"] == only
    ]
    if not casos:
        raise typer.BadParameter(f"nenhum caso para {only!r}")

    results = []
    for caso in casos:
        console.print(f"[bold cyan]{caso['id']}[/] {caso['query']}")
        audit = AuditLog(Path(settings.runs_dir), None, enabled=True)
        cache = Cache(settings.db_path, enabled=True)
        orchestrator = Orchestrator(
            settings,
            build_provider(settings),
            cache=cache,
            audit=audit,
            on_event=_progress(False),
        )
        try:
            run = asyncio.run(
                orchestrator.run(
                    caso["query"],
                    mode=caso.get("mode", "standard"),
                    max_depth=caso.get("min_depth", 1),
                )
            )
        finally:
            cache.close()
        save_run(settings, run)
        nota = evaluate(run, caso.get("min_depth", 0))
        nota["case"] = caso["id"]
        results.append(nota)
        console.print(
            f"  score [bold]{nota['score']}[/] | nos {nota['nodes']} | fontes {nota['sources']} "
            f"| llm {nota['llm_calls']} | parado por {nota['stopped_by']}"
        )

    media = sum(r["score"] for r in results) / len(results)
    console.print(f"[bold]media:[/] {media:.3f} em {len(results)} casos")
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            __import__("json").dumps(
                {
                    "generated_at": dt.datetime.now().isoformat(),
                    "average": media,
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        console.print(f"[green]resultado da avaliacao em[/] {out}")


@app.command()
def mcp() -> None:
    """Sobe o servidor MCP (stdio)."""
    from .mcp_server import main

    main()


@app.command()
def doctor(
    offline: bool = typer.Option(False, "--offline", help="so checa caminhos locais"),
) -> None:
    """Verifica SearXNG, LLM, rede e caminhos."""
    settings = get_settings()
    checks = asyncio.run(run_doctor(settings, offline=offline))
    console.print(format_checks(checks))
    raise typer.Exit(0 if all(c.ok for c in checks) else 1)


@app.command()
def schema(out: Path | None = typer.Option(None, "--out")) -> None:
    """Exporta o JSON Schema da saida (schema/abstraction.schema.json)."""
    path = export_schema(out)
    console.print(f"[green]schema em[/] {path}")


@app.command()
def setup(
    provider: str | None = typer.Argument(None, help="Provider a configurar (opcional)"),
    skip_test: bool = typer.Option(False, "--skip-test", help="Pula teste de conexão"),
) -> None:
    """Wizard interativo para configurar o provider LLM."""
    from .setup import run_setup
    run_setup(provider_name=provider, skip_test=skip_test)


config_app = typer.Typer(help="Gerencia configurações do abstrator.")
app.add_typer(config_app, name="config")


@config_app.command("provider")
def config_provider(
    name: str = typer.Argument(..., help="Nome do provider"),
    model: str | None = typer.Option(None, "--model", "-m", help="Modelo a usar"),
) -> None:
    """Alterna o provider LLM sem passar pelo wizard completo.

    Providers: claude_code_cli, anthropic, openrouter, gemini_cli, opencode_zen, ollama
    """
    from .setup import PROVIDERS, DEFAULT_MODELS, _write_env, _read_env
    if name not in PROVIDERS:
        valid = ", ".join(PROVIDERS.keys())
        console.print(f"[red]Provider inválido.[/] Use um de: {valid}")
        raise typer.Exit(1)

    updates: dict[str, str] = {"ABSTRATOR_LLM_PROVIDER": name}
    if model:
        updates["ABSTRATOR_LLM_MODEL"] = model
    elif name in DEFAULT_MODELS and DEFAULT_MODELS[name]:
        updates["ABSTRATOR_LLM_MODEL"] = DEFAULT_MODELS[name]

    _write_env(updates)
    reset_settings_cache()

    info = PROVIDERS[name]
    console.print(f"[green]✓[/] Provider alterado para [bold]{info['label']}[/]")
    if updates.get("ABSTRATOR_LLM_MODEL"):
        console.print(f"  Modelo: {updates['ABSTRATOR_LLM_MODEL']}")
    if info["keys"]:
        missing = [k for k in info["keys"] if not _read_env().get(k)]
        if missing:
            console.print(f"[yellow]⚠ Chaves ausentes: {', '.join(missing)}[/]")
            console.print(f"  {info['check_msg']}")
            console.print(f"  Configure com: abstrator setup {name}")


@config_app.command("show")
def config_show() -> None:
    """Mostra a configuração atual do provider."""
    from .setup import PROVIDERS, show_provider_table
    settings = get_settings()
    console.print(f"Provider atual: [bold cyan]{settings.llm_provider}[/]")
    console.print(f"Modelo: [dim]{settings.llm_model}[/]")
    console.print()
    show_provider_table(settings.llm_provider)


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
