from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import NodeStatus, Run

EVAL_QUERIES: list[dict[str, Any]] = [
    {
        "id": "q01",
        "query": "app de busca de viagens com opcoes gratuitas",
        "mode": "standard",
        "kind": "practical",
        "min_depth": 1,
    },
    {
        "id": "q02",
        "query": "como cachear respostas de LLM sem perder qualidade",
        "mode": "standard",
        "kind": "practical",
        "min_depth": 1,
    },
    {
        "id": "q03",
        "query": "scraping etico de sites de viagem",
        "mode": "standard",
        "kind": "practical",
        "min_depth": 1,
    },
    {
        "id": "q04",
        "query": "rate limiting em APIs publicas sem ser bloqueado",
        "mode": "quick",
        "kind": "practical",
        "min_depth": 0,
    },
    {
        "id": "q05",
        "query": "agentes de IA: orquestracao com ferramentas",
        "mode": "standard",
        "kind": "practical",
        "min_depth": 1,
    },
    {
        "id": "q06",
        "query": "como especialistas melhoram ferramentas de pesquisa?",
        "mode": "standard",
        "kind": "theoretical",
        "min_depth": 1,
    },
    {
        "id": "q07",
        "query": "abstracao recursiva emInterfaces de usuario",
        "mode": "standard",
        "kind": "theoretical",
        "min_depth": 1,
    },
    {
        "id": "q08",
        "query": "divisao do trabalho para conquistar em pesquisa",
        "mode": "quick",
        "kind": "theoretical",
        "min_depth": 0,
    },
    {
        "id": "q09",
        "query": "avaliacao de qualidade de sistemas de recuperacao",
        "mode": "standard",
        "kind": "mixed",
        "min_depth": 1,
    },
    {
        "id": "q10",
        "query": "guardrails de seguranca para agentes autonomos",
        "mode": "standard",
        "kind": "mixed",
        "min_depth": 1,
    },
]


@dataclass(slots=True)
class Criterion:
    name: str
    score: float
    weight: float
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": round(self.score, 3),
            "weight": self.weight,
            "detail": self.detail,
        }


def _ratio(numerator: float, denominator: float) -> float:
    return 0.0 if denominator <= 0 else numerator / denominator


def evaluate(run: Run, expected_depth: int = 0) -> dict[str, Any]:
    """Rubrica offline e deterministica: mede estrutura, citacao e eficiencia."""
    nodes = list(run.nodes.values())
    researched = [n for n in nodes if n.analysis.meaning or n.analysis.practice]
    claims = [c for n in nodes for c in n.analysis.best_practices]
    views = [v for n in nodes for v in n.analysis.expert_views]
    cited = [c for c in claims if c.source_ids]
    cited_views = [v for v in views if v.source_ids]
    leaves = [n for n in nodes if n.status is NodeStatus.LEAF and not n.children]
    with_sources = [n for n in leaves if n.analysis.best_practices or n.analysis.existing_tools]
    max_depth = max((n.depth for n in nodes), default=0)

    criteria = [
        Criterion(
            "estrutura",
            _ratio(len(researched), len(nodes)),
            0.2,
            f"{len(researched)}/{len(nodes)} nos com analise",
        ),
        Criterion(
            "citacao",
            _ratio(len(cited) + len(cited_views), len(claims) + len(views)),
            0.25,
            f"{len(cited)}/{len(claims)} claims e {len(cited_views)}/{len(views)} "
            "opinioes com source_id",
        ),
        Criterion(
            "fontes_por_folha",
            _ratio(len(with_sources), len(leaves)),
            0.15,
            f"{len(with_sources)}/{len(leaves)} folhas com conteudo citado",
        ),
        Criterion(
            "profundidade",
            _ratio(min(max_depth, 3), max(3, expected_depth + 1)),
            0.1,
            f"profundidade maxima {max_depth} (esperado >= {expected_depth})",
        ),
        Criterion(
            "trilha_de_aprendizado",
            1.0 if run.learning_path and run.learning_path[-1] == run.root_id else 0.0,
            0.1,
            f"trilha com {len(run.learning_path)} nos, terminando na raiz",
        ),
        Criterion(
            "sintese",
            _ratio(
                (1 if run.summary else 0) + _ratio(len(run.recommendations), 3),
                1 + 1,
            ),
            0.15,
            f"resumo {'ok' if run.summary else 'vazio'}, {len(run.recommendations)} recomendacoes",
        ),
        Criterion(
            "eficiencia",
            _ratio(min(len(nodes), 12), max(run.budget.llm_calls, 1)),
            0.05,
            f"{len(nodes)} nos para {run.budget.llm_calls} chamadas LLM",
        ),
    ]
    total = sum(c.score * c.weight for c in criteria)
    return {
        "run_id": run.run_id,
        "query": run.query,
        "score": round(total, 3),
        "criteria": [c.to_dict() for c in criteria],
        "nodes": len(nodes),
        "sources": len(run.sources),
        "llm_calls": run.budget.llm_calls,
        "stopped_by": run.budget.stopped_by,
    }


def load_queries(path: str | None = None) -> list[dict[str, Any]]:
    if path:
        import json
        from pathlib import Path

        return json.loads(Path(path).read_text(encoding="utf-8"))
    return EVAL_QUERIES
