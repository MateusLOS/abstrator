from __future__ import annotations

import logging
from typing import Any

from ..models import (
    AdvancedMethod,
    Analysis,
    CreditedClaim,
    ExistingTool,
    ExpertView,
    Integration,
    Lens,
    LensFinding,
    Node,
    Recommendation,
    RootSynthesis,
    Run,
)
from ..prompts import render
from .llm_runner import LLMRunner

log = logging.getLogger(__name__)


def _clean(ids: list[str], valid: set[str]) -> list[str]:
    out: list[str] = []
    for sid in ids:
        sid = sid.strip()
        if sid in valid and sid not in out:
            out.append(sid)
    return out


def analysis_from_findings(
    findings: dict[Lens, LensFinding],
    integration: Integration | None,
    valid_source_ids: set[str],
) -> tuple[Analysis, float]:
    """Monta a Analysis final a partir das lentes + integracao, exigindo citacoes."""
    uncited: list[str] = []
    best_practices: list[CreditedClaim] = []
    expert_views: list[ExpertView] = []
    methods: list[AdvancedMethod] = []
    tools: list[ExistingTool] = []
    confidences: list[float] = []

    def ingest(lens: Lens) -> LensFinding | None:
        finding = findings.get(lens)
        if finding is None:
            return None
        confidences.append(finding.confidence)
        for claim in finding.claims:
            kept = _clean(claim.source_ids, valid_source_ids)
            if kept:
                best_practices.append(CreditedClaim(text=claim.text, source_ids=kept))
            elif claim.text.strip():
                uncited.append(claim.text)
        for view in finding.expert_views:
            kept = _clean(view.source_ids, valid_source_ids)
            if kept and view.claim.strip():
                expert_views.append(
                    ExpertView(
                        who=view.who or "especialista nao identificado",
                        claim=view.claim,
                        source_ids=kept,
                    )
                )
        for method in finding.advanced_methods:
            kept = _clean(method.source_ids, valid_source_ids)
            methods.append(
                AdvancedMethod(
                    name=method.name,
                    when_to_use=method.when_to_use,
                    fit_score=method.fit_score,
                    source_ids=kept,
                )
            )
        for tool in finding.tools:
            if not tool.name.strip():
                continue
            tools.append(
                ExistingTool(
                    name=tool.name,
                    free=tool.free,
                    url=tool.url,
                    note=tool.note,
                    source_ids=_clean(tool.source_ids, valid_source_ids),
                )
            )
        uncited.extend(finding.uncited_claims)
        return finding

    for lens in (
        Lens.BEST_PRACTICES,
        Lens.EXPERT_VIEWS,
        Lens.ADVANCED_METHODS,
        Lens.EXISTING_TOOLS,
    ):
        ingest(lens)

    meaning = _first(findings, Lens.MEANING)
    analogy = _analogies(findings.get(Lens.ANALOGY))
    theory = _first(findings, Lens.THEORY)
    practice = _first(findings, Lens.PRACTICE)

    open_questions = list(integration.open_questions) if integration else []
    for text in uncited[:10]:
        open_questions.append(f"afirmacao sem fonte (descartada): {text[:160]}")

    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    if integration is not None and integration.confidence:
        confidence = confidence * 0.6 + integration.confidence * 0.4

    analysis = Analysis(
        meaning=meaning or (integration.meaning if integration else ""),
        analogy=analogy,
        theory=theory or (integration.theory if integration else ""),
        practice=practice or (integration.practice if integration else ""),
        best_practices=best_practices,
        expert_views=expert_views,
        advanced_methods=methods,
        existing_tools=tools,
        fit_to_goal=integration.fit_to_goal if integration else "",
        consensus=integration.consensus if integration else "",
        conflicts=list(integration.conflicts) if integration else [],
        open_questions=open_questions,
    )
    return analysis, round(confidence, 4)


def _first(findings: dict[Lens, LensFinding], lens: Lens) -> str:
    finding = findings.get(lens)
    return finding.summary.strip() if finding else ""


def _analogies(finding: LensFinding | None) -> str:
    if finding is None:
        return ""
    items = [a for a in finding.analogies if a.strip()]
    if items:
        return "; ".join(items)
    return finding.summary.strip()


async def integrate(
    runner: LLMRunner,
    concept: str,
    goal: str,
    children: list[Node],
    own_findings: dict[Lens, LensFinding] | None = None,
) -> Integration:
    """Sintese de baixo para cima: as partes (do simples ao complexo) viram o pai."""
    child_lines = [
        f"- {c.concept} [{c.id}] (status={c.status.value}, confianca={c.confidence:.2f})"
        for c in children
    ]
    summaries = []
    for child in children:
        bits = [
            child.analysis.meaning[:200],
            child.analysis.practice[:200],
            child.analysis.fit_to_goal[:160],
        ]
        summaries.append(f"- {child.concept}: " + " ".join(b for b in bits if b).strip())
    own = own_findings or {}
    own_lines = [f"- {lens.value}: {f.summary[:200]}" for lens, f in own.items() if f.summary]
    prompt = render(
        "integrate",
        concept=concept,
        goal=goal or "(nao informado)",
        children="\n".join(child_lines) or "(sem sub-conceitos)",
        child_summaries="\n".join(summaries) or "(nenhum)",
        own_summaries="\n".join(own_lines),
    )
    return await runner.run(Integration, stage="integrate", prompt=prompt)


async def synthesize_root(
    runner: LLMRunner, run: Run, goal: str, recommendations_by_node: list[str]
) -> tuple[str, list[Recommendation], list[str], list[str]]:
    """Resumo + recomendacoes da raiz, com ids validados contra a arvore real."""
    path_lines = []
    for node_id in run.learning_path:
        node = run.nodes.get(node_id)
        if node is None:
            continue
        path_lines.append(
            f"- {node_id} [{node.depth}] {node.concept}: {node.analysis.meaning[:180]}"
        )
    source_lines = [
        f"- {sid}: {s.title or s.url} <{s.url}>" for sid, s in list(run.sources.items())[:40]
    ]
    prompt = render(
        "synthesize",
        query=run.query,
        goal=goal or "(nao informado)",
        intent_type=run.intent.type.value,
        constraints=", ".join(run.intent.constraints) or "(nenhuma)",
        learning_path="\n".join(path_lines),
        recommendations="\n".join(recommendations_by_node) or "(nenhuma)",
        sources="\n".join(source_lines),
    )
    result: RootSynthesis = await runner.run(RootSynthesis, stage="synthesize", prompt=prompt)
    valid_nodes = set(run.nodes)
    valid_sources = set(run.sources)
    recommendations: list[Recommendation] = []
    for rec in result.recommendations:
        if not rec.text.strip():
            continue
        node_ids = [n for n in rec.node_ids if n in valid_nodes]
        source_ids = [s for s in rec.source_ids if s in valid_sources]
        if not node_ids:
            continue
        recommendations.append(
            Recommendation(
                text=rec.text, node_ids=node_ids, source_ids=source_ids, rationale=rec.rationale
            )
        )
    return result.summary.strip(), recommendations, result.conflicts, result.open_questions


def remap_analysis(analysis: Analysis, mapping: dict[str, str]) -> Analysis:
    """Reaponta as citacoes para os ids da run atual (cache entre execucoes)."""

    def fix(ids: list[str]) -> list[str]:
        out: list[str] = []
        for sid in ids:
            target = mapping.get(sid, sid)
            if target not in out:
                out.append(target)
        return out

    return Analysis(
        meaning=analysis.meaning,
        analogy=analysis.analogy,
        theory=analysis.theory,
        practice=analysis.practice,
        best_practices=[
            CreditedClaim(text=c.text, source_ids=fix(c.source_ids))
            for c in analysis.best_practices
        ],
        expert_views=[
            ExpertView(who=v.who, claim=v.claim, source_ids=fix(v.source_ids))
            for v in analysis.expert_views
        ],
        advanced_methods=[
            AdvancedMethod(
                name=m.name,
                when_to_use=m.when_to_use,
                fit_score=m.fit_score,
                source_ids=fix(m.source_ids),
            )
            for m in analysis.advanced_methods
        ],
        existing_tools=[
            ExistingTool(
                name=t.name,
                free=t.free,
                url=t.url,
                note=t.note,
                source_ids=fix(t.source_ids),
            )
            for t in analysis.existing_tools
        ],
        fit_to_goal=analysis.fit_to_goal,
        consensus=analysis.consensus,
        conflicts=list(analysis.conflicts),
        open_questions=list(analysis.open_questions),
    )


def cited_sources(analysis: Analysis) -> set[str]:
    ids: set[str] = set()
    for group in (
        analysis.best_practices,
        analysis.expert_views,
        analysis.advanced_methods,
        analysis.existing_tools,
    ):
        for item in group:
            ids.update(item.source_ids)
    return ids


def node_summary(node: Node) -> str:
    parts: list[str] = []
    if node.analysis.practice:
        parts.append(node.analysis.practice[:160])
    if node.analysis.best_practices:
        parts.append("pratica: " + node.analysis.best_practices[0].text[:160])
    if node.analysis.existing_tools:
        names = ", ".join(t.name for t in node.analysis.existing_tools[:3])
        parts.append(f"ferramentas: {names}")
    return " ".join(parts)


def findings_payload(findings: dict[Lens, LensFinding]) -> dict[str, Any]:
    return {lens.value: finding.model_dump(mode="json") for lens, finding in findings.items()}
