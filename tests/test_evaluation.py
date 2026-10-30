from __future__ import annotations

from abstrator.engine.orchestrator import Orchestrator
from abstrator.evaluation import EVAL_QUERIES, evaluate, load_queries
from abstrator.llm import FakeLLM
from abstrator.models import (
    Analysis,
    CreditedClaim,
    Node,
    NodeStatus,
    Recommendation,
    Run,
    Source,
)
from abstrator.search.cache import Cache


def _full_run() -> Run:
    return Run(
        run_id="r_eval",
        query="app de viagens",
        root_id="n1",
        summary="resumo",
        recommendations=[
            Recommendation(text="comece pelo cache", node_ids=["n2"], source_ids=["s1"])
        ],
        nodes={
            "n1": Node(
                id="n1",
                concept="raiz",
                depth=0,
                children=["n2"],
                status=NodeStatus.SYNTHESIZED,
                analysis=Analysis(meaning="m", practice="p"),
            ),
            "n2": Node(
                id="n2",
                concept="folha",
                parent_id="n1",
                depth=1,
                status=NodeStatus.LEAF,
                analysis=Analysis(
                    meaning="m2",
                    best_practices=[CreditedClaim(text="regra", source_ids=["s1"])],
                ),
            ),
        },
        sources={"s1": Source(url="https://a.org", type="academic")},
        learning_path=["n2", "n1"],
    )


def test_evaluate_perfect_run_is_high_score():
    nota = evaluate(_full_run(), expected_depth=1)
    assert nota["score"] > 0.8
    nomes = {c["name"] for c in nota["criteria"]}
    assert {"estrutura", "citacao", "trilha_de_aprendizado", "sintese"} <= nomes


def test_evaluate_penalizes_uncited_claims():
    run = _full_run()
    run.nodes["n2"].analysis.best_practices = [
        CreditedClaim(text="regra sem fonte", source_ids=[]),
        CreditedClaim(text="outra sem fonte", source_ids=[]),
    ]
    nota = evaluate(run, expected_depth=1)
    citacao = next(c for c in nota["criteria"] if c["name"] == "citacao")
    assert citacao["score"] == 0.0
    assert nota["score"] < 0.9


def test_evaluate_detects_empty_tree():
    run = Run(
        run_id="r_vazio",
        query="q",
        root_id="n1",
        nodes={"n1": Node(id="n1", concept="raiz", depth=0)},
        learning_path=[],
    )
    nota = evaluate(run)
    assert nota["score"] < 0.3
    trilha = next(c for c in nota["criteria"] if c["name"] == "trilha_de_aprendizado")
    assert trilha["score"] == 0.0


def test_eval_set_has_practical_and_theoretical_queries():
    kinds = {c["kind"] for c in EVAL_QUERIES}
    assert kinds == {"practical", "theoretical", "mixed"}
    assert len(EVAL_QUERIES) == 10
    assert all(c["id"].startswith("q") for c in EVAL_QUERIES)


def test_load_queries_default_returns_reference_set():
    assert load_queries() == EVAL_QUERIES


async def test_evaluate_works_on_a_real_fake_run(settings, fake_search, fake_fetcher):
    orch = Orchestrator(settings, FakeLLM(), search=fake_search, fetcher=fake_fetcher)
    run = await orch.run("app de viagens", mode="quick", max_depth=1)
    nota = evaluate(run, expected_depth=1)

    assert 0.0 <= nota["score"] <= 1.0
    assert nota["nodes"] == len(run.nodes)


async def test_concept_cache_reuses_node_across_runs(settings, fake_search, fake_fetcher, tmp_path):
    cache = Cache(tmp_path / "c.sqlite3")
    settings.concept_cache_ttl_hours = 24
    settings.cache_ttl_hours = 24

    first = Orchestrator(settings, FakeLLM(), cache=cache, search=fake_search, fetcher=fake_fetcher)
    run1 = await first.run("cache entre runs", mode="quick", max_depth=0)
    assert run1.nodes[run1.root_id].stop_reason is None

    second_search_queries = []
    first_calls = len(fake_search.queries)
    second = Orchestrator(
        settings, FakeLLM(), cache=cache, search=fake_search, fetcher=fake_fetcher
    )
    run2 = await second.run("cache entre runs", mode="quick", max_depth=0)
    second_search_queries.extend(fake_search.queries[first_calls:])

    root = run2.nodes[run2.root_id]
    assert root.notes, "o no reutORIZado deve dizer que veio do cache"
    assert any("cache de conceitos" in note for note in root.notes)
    assert root.analysis.meaning
    assert second_search_queries == []
    run2.validate_tree()
    cache.close()
