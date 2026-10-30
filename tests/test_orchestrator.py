from __future__ import annotations

import json
from pathlib import Path

import pytest

from abstrator.engine.orchestrator import Orchestrator
from abstrator.llm import FakeLLM
from abstrator.models import Node, NodeStatus, Run, StopReason
from abstrator.schema import build_schema


def make_orchestrator(settings, provider, fake_search, fake_fetcher, **kwargs) -> Orchestrator:
    return Orchestrator(
        settings,
        provider,
        search=fake_search,
        fetcher=fake_fetcher,
        **kwargs,
    )


async def test_run_respects_max_depth(settings, provider, fake_search, fake_fetcher):
    orch = make_orchestrator(settings, provider, fake_search, fake_fetcher)
    run = await orch.run("app de busca de viagens", mode="quick", max_depth=1, max_nodes=20)

    assert run.mode.value == "quick"
    assert run.root_id in run.nodes
    assert max(node.depth for node in run.nodes.values()) <= 1
    assert len(run.nodes) <= 20


async def test_run_respects_max_nodes(settings, provider, fake_search, fake_fetcher):
    orch = make_orchestrator(settings, provider, fake_search, fake_fetcher)
    run = await orch.run("arquitetura distribuida", mode="deep", max_nodes=3)

    # nos que batem no limite nao entram na arvore
    assert len(run.nodes) <= 3
    assert run.budget.stopped_by == StopReason.MAX_NODES.value


async def test_learning_path_is_post_order(settings, provider, fake_search, fake_fetcher):
    orch = make_orchestrator(settings, provider, fake_search, fake_fetcher)
    run = await orch.run("pesquisa por abstracao", mode="standard", max_depth=2)

    assert run.learning_path[-1] == run.root_id
    position = {node_id: i for i, node_id in enumerate(run.learning_path)}
    for node_id in run.learning_path:
        for child_id in run.nodes[node_id].children:
            assert position[child_id] < position[node_id]
    assert run.learning_path[0] != run.root_id


async def test_memoization_avoids_duplicate_research(settings, provider, fake_search, fake_fetcher):
    same = {"subs": [{"concept": "camada comum", "kind": "part", "rationale": ""}]}
    provider = FakeLLM(
        script={
            "Decomposition": [
                {
                    "subs": [
                        {"concept": "camada A", "kind": "part", "rationale": ""},
                        {"concept": "camada B", "kind": "part", "rationale": ""},
                    ]
                },
                same,
                same,
                same,
                same,
            ]
        }
    )
    orch = make_orchestrator(settings, provider, fake_search, fake_fetcher)
    run = await orch.run("reduzir custo de LLM", mode="standard", max_depth=2, max_fanout=2)

    common = [n for n in run.nodes.values() if n.concept == "camada comum"]
    assert len(common) == 2
    memo = [n for n in common if n.stop_reason is StopReason.MEMOIZED]
    assert len(memo) == 1
    original = [n for n in common if n.stop_reason is not StopReason.MEMOIZED][0]
    assert memo[0].memoized_from == original.id
    assert memo[0].analysis.meaning == original.analysis.meaning


async def test_stagnation_does_not_create_equal_children(
    settings, provider, fake_search, fake_fetcher
):
    provider = FakeLLM(
        script={
            "Decomposition": {
                "subs": [
                    {"concept": "app de viagens", "kind": "part", "rationale": ""},
                    {"concept": "app de viagem", "kind": "part", "rationale": ""},
                ]
            }
        }
    )
    orch = make_orchestrator(settings, provider, fake_search, fake_fetcher)
    run = await orch.run("app de viagens", mode="standard", max_depth=3)

    root = run.nodes[run.root_id]
    assert root.children == []
    assert root.stop_reason is StopReason.STAGNATION


async def test_cancellation_returns_partial_tree(settings, provider, fake_search, fake_fetcher):
    events: list[dict] = []

    def on_event(event: dict) -> None:
        events.append(event)
        if event.get("event") == "node_done":
            orch.cancel()

    orch = make_orchestrator(settings, provider, fake_search, fake_fetcher, on_event=on_event)
    run = await orch.run("cancelar cedo", mode="standard", max_depth=3)

    assert run.nodes
    assert run.budget.stopped_by == StopReason.CANCELLED.value
    assert any("cancelada" in w for w in run.warnings)


async def test_budget_stop_produces_partial_tree(settings, provider, fake_search, fake_fetcher):
    settings.budget_max_llm_calls = 4
    settings.budget_max_pages = 3
    orch = make_orchestrator(settings, provider, fake_search, fake_fetcher)
    run = await orch.run("orçamento apertado", mode="standard", max_depth=3)

    assert run.nodes
    assert run.budget.stopped_by == StopReason.BUDGET.value
    assert (
        any(n.status is NodeStatus.BUDGET_STOPPED for n in run.nodes.values())
        or run.budget.llm_calls <= settings.budget_max_llm_calls
    )


async def test_output_validates_against_schema(settings, provider, fake_search, fake_fetcher):
    orch = make_orchestrator(settings, provider, fake_search, fake_fetcher)
    run = await orch.run("validacao de saida", mode="quick", max_depth=1)
    payload = run.model_dump(mode="json")
    json.dumps(payload)  # serializa sem Typeshow

    schema = build_schema()
    assert schema["title"] == "Run"
    Run.model_validate(payload)
    run.validate_tree()


async def test_every_cited_source_exists(settings, provider, fake_search, fake_fetcher):
    orch = make_orchestrator(settings, provider, fake_search, fake_fetcher)
    run = await orch.run("fontes citadas", mode="standard", max_depth=1)

    for node in run.nodes.values():
        for claim in node.analysis.best_practices:
            assert claim.source_ids
            assert set(claim.source_ids) <= set(run.sources)
        for view in node.analysis.expert_views:
            assert set(view.source_ids) <= set(run.sources)


async def test_progress_events_are_emitted(settings, provider, fake_search, fake_fetcher):
    events: list[dict] = []
    orch = make_orchestrator(settings, provider, fake_search, fake_fetcher, on_event=events.append)
    await orch.run("eventos", mode="quick", max_depth=1)

    kinds = {e["event"] for e in events}
    assert {"start", "node_start", "node_done", "done", "llm"} <= kinds


def test_run_validation_detects_bad_tree():
    with pytest.raises(ValueError):
        Run(
            run_id="r1",
            query="q",
            root_id="n1",
            budget={
                "max_queries": 1,
                "max_pages": 1,
                "max_llm_calls": 1,
                "max_tokens": 1,
                "max_seconds": 1.0,
                "max_usd": 1.0,
            },
            nodes={
                "n1": Node(id="n1", concept="a", depth=0, children=["n2"]),
                "n2": Node(id="n2", concept="b", depth=1, parent_id="nX"),
            },
        ).validate_tree()


def test_schema_file_matches_models(tmp_path: Path):
    from abstrator.schema import export_schema

    path = export_schema(tmp_path / "schema.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["properties"]["learning_path"]
    assert data["properties"]["nodes"]
    assert data["properties"]["sources"]


async def test_audit_trail_is_written(
    tmp_path: Path, settings, provider, fake_search, fake_fetcher
):
    from abstrator.audit import AuditLog

    audit = AuditLog(Path(settings.runs_dir), None)
    orch = make_orchestrator(settings, provider, fake_search, fake_fetcher, audit=audit)
    run = await orch.run("auditoria", mode="quick", max_depth=1)

    records = list(AuditLog.read(Path(settings.runs_dir) / run.run_id))
    events = {r["event"] for r in records}
    assert {"llm", "node_start", "node_done", "run_finished"} <= events
    assert all(r["run_id"] == run.run_id for r in records)
