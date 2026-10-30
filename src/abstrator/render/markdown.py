from __future__ import annotations

from ..models import Node, Run


def _cite(ids: list[str]) -> str:
    return " ".join(f"[{sid}]" for sid in ids)


def render_markdown(run: Run) -> str:
    lines: list[str] = []
    add = lines.append

    add(f"# {run.query}")
    add("")
    add(f"- **run**: `{run.run_id}`")
    add(f"- **modo**: {run.mode.value}")
    add(f"- **criado em**: {run.created_at:%Y-%m-%d %H:%M:%S} UTC")
    if run.intent.goal:
        add(f"- **objetivo**: {run.intent.goal}")
    if run.intent.constraints:
        add(f"- **restricoes**: {', '.join(run.intent.constraints)}")
    add(
        f"- **orcamento**: {run.budget.llm_calls}/{run.budget.max_llm_calls} chamadas LLM, "
        f"{run.budget.queries}/{run.budget.max_queries} buscas, "
        f"{run.budget.pages}/{run.budget.max_pages} paginas, "
        f"{run.budget.seconds:.1f}s, ${run.budget.usd:.4f}"
        + (f" (parou por {run.budget.stopped_by})" if run.budget.stopped_by else "")
    )
    add("")

    if run.summary:
        add("## Resumo")
        add("")
        add(run.summary)
        add("")

    if run.recommendations:
        add("## Recomendacoes")
        add("")
        for i, rec in enumerate(run.recommendations, start=1):
            target = ", ".join(f"`{n}`" for n in rec.node_ids)
            add(f"{i}. {rec.text}" + (f" ({target} {_cite(rec.source_ids)})" if target else ""))
            if rec.rationale:
                add(f"   - por que: {rec.rationale}")
        add("")

    add("## Trilha de aprendizado (do simples ao complexo)")
    add("")
    for pos, node_id in enumerate(run.learning_path, start=1):
        node = run.nodes.get(node_id)
        if node is None:
            continue
        add(f"{pos}. **[{node_id}] {node.concept}** — {node.analysis.meaning[:220]}")
    add("")

    add("## Arvore de conceitos")
    add("")
    _render_tree(run, run.root_id, depth=0, add=add)

    add("")
    add("## Detalhe por no")
    add("")
    for node_id in run.learning_path:
        node = run.nodes.get(node_id)
        if node is None:
            continue
        add(f"### {node_id} — {node.concept}")
        add("")
        add(
            f"profundidade {node.depth} · status {node.status.value} · "
            f"confianca {node.confidence:.2f}"
            + (f" · parada: {node.stop_reason.value}" if node.stop_reason else "")
        )
        if node.complexity:
            add(f"complexidade: {node.complexity.score:.2f} ({node.complexity.verdict.value})")
        add("")
        _analysis_block(node, add)
        if node.notes:
            add(f"**Notas**: {'; '.join(node.notes)}")
            add("")

    add("## Fontes")
    add("")
    for sid, source in run.sources.items():
        cred = f"{source.credibility:.2f}"
        label = f"{source.type.value}, credibilidade {cred}"
        add(f"- **[{sid}]** ({label}) {source.title or source.url}")
        add(f"  <{source.url}>")
    add("")

    if run.warnings:
        add("## Avisos")
        add("")
        for warning in run.warnings:
            add(f"- {warning}")
        add("")

    return "\n".join(lines)


def _analysis_block(node: Node, add) -> None:
    analysis = node.analysis
    if analysis.meaning:
        add(f"**Significado**: {analysis.meaning}")
        add("")
    if analysis.analogy:
        add(f"**Analogia**: {analysis.analogy}")
        add("")
    if analysis.theory:
        add(f"**Teoria**: {analysis.theory}")
        add("")
    if analysis.practice:
        add(f"**Pratica**: {analysis.practice}")
        add("")
    if analysis.fit_to_goal:
        add(f"**Adequacao ao objetivo**: {analysis.fit_to_goal}")
        add("")
    if analysis.best_practices:
        add("**Boas praticas**:")
        add("")
        for claim in analysis.best_practices:
            add(f"- {claim.text} {_cite(claim.source_ids)}")
        add("")
    if analysis.expert_views:
        add("**O que dizem especialistas**:")
        add("")
        for view in analysis.expert_views:
            add(f"- {view.who}: {view.claim} {_cite(view.source_ids)}")
        add("")
    if analysis.advanced_methods:
        add("**Metodos avancados**:")
        add("")
        for method in analysis.advanced_methods:
            add(
                f"- {method.name} (fit {method.fit_score:.2f}, usar quando: {method.when_to_use}) "
                f"{_cite(method.source_ids)}"
            )
        add("")
    if analysis.existing_tools:
        add("**Ferramentas existentes**:")
        add("")
        for tool in analysis.existing_tools:
            free = "gratuita" if tool.free else "paga"
            url = f" <{tool.url}>" if tool.url else ""
            add(f"- {tool.name} ({free}){url}")
        add("")
    if analysis.consensus:
        add(f"**Consenso**: {analysis.consensus}")
        add("")
    if analysis.conflicts:
        add("**Conflitos**:")
        add("")
        for conflict in analysis.conflicts:
            add(f"- {conflict}")
        add("")
    if analysis.open_questions:
        add("**Em aberto**:")
        add("")
        for question in analysis.open_questions:
            add(f"- {question}")
        add("")


def _render_tree(run: Run, node_id: str, depth: int, add) -> None:
    node = run.nodes.get(node_id)
    if node is None:
        return
    indent = "  " * depth
    marker = "" if node.status.value == "synthesized" else f" _({node.status.value})_"
    add(f"{indent}- **{node_id}** {node.concept}{marker}")
    for child_id in node.children:
        _render_tree(run, child_id, depth + 1, add)
