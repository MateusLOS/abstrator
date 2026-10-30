from __future__ import annotations

import pytest

from abstrator.config import IdFactory
from abstrator.engine.budget import BudgetTracker
from abstrator.engine.llm_runner import LLMRunner
from abstrator.engine.synthesize import (
    analysis_from_findings,
    integrate,
    synthesize_root,
)
from abstrator.llm import FakeLLM
from abstrator.models import (
    CreditedClaimDraft,
    ExpertViewDraft,
    Integration,
    Lens,
    LensFinding,
    Node,
    Run,
)


def _findings(valid: set[str]) -> dict[Lens, LensFinding]:
    return {
        Lens.MEANING: LensFinding(summary="significado testado"),
        Lens.ANALOGY: LensFinding(summary="parece uma receita"),
        Lens.THEORY: LensFinding(summary="teoria testada"),
        Lens.PRACTICE: LensFinding(summary="passo a passo testado"),
        Lens.BEST_PRACTICES: LensFinding(
            summary="regras",
            claims=[
                CreditedClaimDraft(text="regra com fonte", source_ids=[sorted(valid)[0]]),
                CreditedClaimDraft(text="regra sem fonte", source_ids=[]),
                CreditedClaimDraft(text="regra com id inventado", source_ids=["s99"]),
            ],
        ),
        Lens.EXPERT_VIEWS: LensFinding(
            expert_views=[ExpertViewDraft(who="Dra. X", claim="claim", source_ids=list(valid))],
        ),
        Lens.ADVANCED_METHODS: LensFinding(
            advanced_methods=[
                {
                    "name": "metodo",
                    "when_to_use": "depois do basico",
                    "fit_score": 0.8,
                    "source_ids": list(valid),
                }
            ]
        ),
        Lens.EXISTING_TOOLS: LensFinding(
            tools=[{"name": "Ferramenta X", "free": True, "url": "https://x.dev"}]
        ),
    }


def test_only_cited_claims_survive():
    findings = _findings({"s1", "s2"})
    analysis, confidence = analysis_from_findings(
        findings, Integration(meaning="m", fit_to_goal="g", consensus="c"), {"s1", "s2"}
    )

    textos = [c.text for c in analysis.best_practices]
    assert textos == ["regra com fonte"]
    assert analysis.best_practices[0].source_ids == ["s1"]
    assert any("sem fonte" in q for q in analysis.open_questions)
    assert any("id inventado" in q for q in analysis.open_questions)
    assert 0 < confidence <= 1


def test_lens_fields_map_to_analysis():
    analysis, _ = analysis_from_findings(_findings({"s1"}), None, {"s1"})
    assert analysis.meaning == "significado testado"
    assert analysis.analogy == "parece uma receita"
    assert analysis.theory == "teoria testada"
    assert analysis.practice == "passo a passo testado"
    assert analysis.expert_views[0].who == "Dra. X"
    assert analysis.advanced_methods[0].fit_score == 0.8
    assert analysis.existing_tools[0].free is True


def test_expert_view_without_source_is_dropped():
    findings = {
        Lens.EXPERT_VIEWS: LensFinding(
            expert_views=[ExpertViewDraft(who="Y", claim="sem fonte", source_ids=[])]
        )
    }
    analysis, _ = analysis_from_findings(findings, None, {"s1"})
    assert analysis.expert_views == []


async def test_integrate_uses_children_summaries(settings, provider):
    runner = LLMRunner(settings, provider, BudgetTracker.from_settings(settings, "quick"))
    children = [
        Node(id="n1", concept="parte a", depth=0, analysis={"meaning": "significado a"}),
        Node(
            id="n2",
            concept="parte b",
            depth=1,
            parent_id="n1",
            analysis={"meaning": "significado b"},
        ),
    ]
    integration = await integrate(runner, "pai", "objetivo", children, {})
    assert isinstance(integration, Integration)
    assert provider.calls[-1] == "Integration"


async def test_root_synthesis_drops_unknown_ids(settings, provider):
    runner = LLMRunner(settings, provider, BudgetTracker.from_settings(settings, "quick"))
    run = Run(
        run_id="r1",
        query="q",
        root_id="n1",
        nodes={"n1": Node(id="n1", concept="raiz", depth=0, analysis={"meaning": "m"})},
        learning_path=["n1"],
    )
    provider = FakeLLM(
        script={
            "RootSynthesis": {
                "summary": "resumo final",
                "recommendations": [
                    {
                        "text": "boa",
                        "node_ids": ["n1", "n99"],
                        "source_ids": ["s99"],
                        "rationale": "",
                    },
                    {"text": "orfa", "node_ids": ["n42"], "source_ids": [], "rationale": ""},
                ],
            }
        }
    )
    runner.provider = provider
    summary, recommendations, conflicts, questions = await synthesize_root(
        runner, run, "objetivo", []
    )

    assert summary == "resumo final"
    assert len(recommendations) == 1
    assert recommendations[0].node_ids == ["n1"]
    assert recommendations[0].source_ids == []
    assert conflicts == [] and questions == []


def test_source_registry_is_url_keyed():
    from abstrator.engine.research import SourceRegistry

    registry = SourceRegistry(IdFactory())
    first = registry.register("https://a.org/x", "A", "resumo")
    again = registry.register("https://a.org/x", "A2", "resumo2")

    assert first == again
    assert registry.exists("https://a.org/x")
    assert registry.sources[first].title == "A"


@pytest.mark.parametrize(
    ("url", "expected_type"),
    [
        ("https://arxiv.org/abs/1234", "academic"),
        ("https://docs.python.org/3/x", "official_docs"),
        ("https://stackoverflow.com/q/1", "forum"),
        ("https://github.com/user/repo", "vendor"),
    ],
)
def test_credibility_classification(url, expected_type):
    from abstrator.search.credibility import classify

    assert classify(url, "", "").type.value == expected_type
