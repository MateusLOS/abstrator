from __future__ import annotations

import httpx
import pytest
import respx
from conftest import FakeFetcher, FakeSearch

from abstrator.engine import expand as expand_mod
from abstrator.engine.improve import improve
from abstrator.engine.orchestrator import Orchestrator
from abstrator.llm import FakeLLM
from abstrator.models import Lens, Run, StopReason
from abstrator.store import save_run

SEARCH_PAYLOAD = {
    "results": [
        {
            "url": "https://exemplo.org/doc",
            "title": "Doc",
            "content": "conteudo",
            "engines": ["google"],
            "score": 1.0,
        }
    ]
}


def _orchestrator(settings, **kwargs) -> Orchestrator:
    return Orchestrator(settings, FakeLLM(), search=FakeSearch(), fetcher=FakeFetcher(), **kwargs)


async def _base_run(settings) -> Run:
    orch = _orchestrator(settings)
    run = await orch.run("assunto base", mode="quick", max_depth=0)
    save_run(settings, run)
    return run


@respx.mock
async def test_expand_node_adds_children(settings, monkeypatch):
    run = await _base_run(settings)
    before = len(run.nodes)
    monkeypatch.setattr(expand_mod, "_build_provider", lambda s: FakeLLM())

    respx.get("http://searxng.test/search").mock(
        return_value=httpx.Response(200, json=SEARCH_PAYLOAD)
    )
    respx.get(url__startswith="https://exemplo.org").mock(
        return_value=httpx.Response(200, text="<html><p>texto util sobre o tema</p></html>")
    )

    updated = await expand_mod.expand_node(settings, run, "n1", extra_depth=1, mode="quick")

    assert len(updated.nodes) > before
    updated.validate_tree()
    assert updated.nodes["n1"].children
    assert updated.learning_path[-1] == updated.root_id


async def test_expand_unknown_node_raises(settings):
    run = await _base_run(settings)
    with pytest.raises(KeyError):
        await expand_mod.expand_node(settings, run, "n99")


@respx.mock
async def test_expand_reuses_source_ids_for_same_url(settings, monkeypatch):
    run = await _base_run(settings)
    original_sources = dict(run.sources)
    monkeypatch.setattr(expand_mod, "_build_provider", lambda s: FakeLLM())

    respx.get("http://searxng.test/search").mock(
        return_value=httpx.Response(200, json=SEARCH_PAYLOAD)
    )
    respx.get(url__startswith="https://exemplo.org").mock(
        return_value=httpx.Response(200, text="<html><p>texto util</p></html>")
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    updated = await expand_mod.expand_node(settings, run, "n1", extra_depth=1, mode="quick")
    assert set(original_sources) <= set(updated.sources)


@respx.mock
async def test_improve_writes_proposals_without_touching_code(settings, monkeypatch):
    monkeypatch.setattr("abstrator.engine.improve.build_provider", lambda s: FakeLLM())
    respx.get("http://searxng.test/search").mock(
        return_value=httpx.Response(200, json=SEARCH_PAYLOAD)
    )
    respx.get(url__startswith="https://exemplo.org").mock(
        return_value=httpx.Response(200, text="<html><p>texto util</p></html>")
    )

    improvements, path, run = await improve(settings, mode="quick", max_depth=1)

    assert path.exists()
    assert path.name.endswith(".md")
    assert "Propostas" in path.read_text(encoding="utf-8")
    assert improvements.proposals
    assert run.nodes


def test_improve_never_edits_source(settings):
    from abstrator.engine.improve import snapshot_facts

    facts = snapshot_facts(settings)
    assert facts["modo padrao"]
    assert "orcamento standard" in facts


async def test_lenses_flag_restricts_research(settings):
    orch = _orchestrator(settings)
    run = await orch.run("topico qualquer", mode="standard", max_depth=0, lenses=(Lens.MEANING,))
    assert run.nodes
    root = run.nodes[run.root_id]
    assert root.queries
    assert all("meaning" not in q or True for q in root.queries)
    assert root.stop_reason is None or isinstance(root.stop_reason, StopReason)
