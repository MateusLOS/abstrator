from __future__ import annotations

from pathlib import Path

import pytest

from abstrator.models import Analysis, CreditedClaim, Node, Run, Source
from abstrator.render.markdown import render_markdown
from abstrator.store import list_runs, load_run, resolve_run_id, save_run


def _run() -> Run:
    return Run(
        run_id="r_teste_1",
        query="app de busca de viagens",
        nodes={
            "n1": Node(
                id="n1",
                concept="app de viagens",
                depth=0,
                status="synthesized",
                confidence=0.8,
                children=["n2"],
                analysis=Analysis(
                    meaning="um app que compara ofertas",
                    practice="comece pelo cache",
                    best_practices=[CreditedClaim(text="use cache", source_ids=["s1"])],
                ),
            ),
            "n2": Node(
                id="n2",
                concept="coleta de dados",
                parent_id="n1",
                depth=1,
                status="leaf",
                confidence=0.6,
                analysis=Analysis(meaning="extrair de varias fontes"),
            ),
        },
        sources={
            "s1": Source(
                url="https://exemplo.org/paper",
                title="Um paper",
                type="academic",
                credibility=0.92,
            )
        },
        learning_path=["n2", "n1"],
        root_id="n1",
        summary="resumo do run",
        recommendations=[],
    )


def test_save_and_load_roundtrip(settings):
    run = _run()
    path = save_run(settings, run)
    directory = Path(settings.runs_dir) / run.run_id

    assert path.name == "result.json"
    assert (directory / "report.md").exists()
    loaded = load_run(settings, run.run_id)
    assert loaded.query == run.query
    assert set(loaded.sources) == {"s1"}


def test_list_runs_returns_metas(settings):
    save_run(settings, _run())
    metas = list_runs(settings)

    assert len(metas) == 1
    assert metas[0].run_id == "r_teste_1"
    assert metas[0].nodes == 2
    assert metas[0].sources == 1


def test_resolve_run_id_accepts_prefix(settings):
    save_run(settings, _run())
    assert resolve_run_id(settings, "r_teste_1") == "r_teste_1"
    with pytest.raises(FileNotFoundError):
        resolve_run_id(settings, "nao_existe")


def test_markdown_contains_structure_and_citations(settings):
    markdown = render_markdown(_run())

    assert "# app de busca de viagens" in markdown
    assert "## Resumo" in markdown
    assert "## Trilha de aprendizado" in markdown
    assert "## Fontes" in markdown
    assert "[s1]" in markdown
    assert "n1" in markdown and "n2" in markdown


def test_save_rejects_broken_tree(settings):
    run = _run()
    run.nodes["n2"].parent_id = "n9"
    with pytest.raises(ValueError):
        save_run(settings, run)
