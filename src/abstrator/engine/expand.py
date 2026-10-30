from __future__ import annotations

import re

from ..config import Settings
from ..models import Node, Run, Source
from .orchestrator import Orchestrator, _post_order

_NUM = re.compile(r"(\d+)$")


def _next_index(prefix: str, existing: list[str]) -> int:
    biggest = 0
    for key in existing:
        match = _NUM.search(key)
        if match and key.startswith(prefix):
            biggest = max(biggest, int(match.group(1)))
    return biggest + 1


def _build_provider(settings: Settings):
    from ..llm import build_provider

    return build_provider(settings)


async def expand_node(
    settings: Settings,
    run: Run,
    node_id: str,
    *,
    extra_depth: int = 1,
    mode: str = "standard",
    on_event=None,
) -> Run:
    """Aprofunda sob demanda um no que parou cedo e mescla o resultado na run."""
    if node_id not in run.nodes:
        raise KeyError(f"node inexistente: {node_id}")
    concept = run.nodes[node_id].concept

    orchestrator = Orchestrator(settings, _build_provider(settings), on_event=on_event)
    try:
        sub = await orchestrator.run(
            concept,
            mode=mode,
            max_depth=max(1, extra_depth),
            goal_context=run.intent.goal,
        )
    finally:
        await orchestrator.aclose()

    node_index = _next_index(settings.node_prefix, list(run.nodes))
    source_index = _next_index(settings.source_prefix, list(run.sources))

    url_to_id = {source.url: sid for sid, source in run.sources.items()}
    source_map: dict[str, str] = {}
    for sid, source in sub.sources.items():
        if source.url in url_to_id:
            source_map[sid] = url_to_id[source.url]
        else:
            new_id = f"{settings.source_prefix}{source_index}"
            source_index += 1
            source_map[sid] = new_id
            run.sources[new_id] = Source.model_validate(source.model_dump(mode="json"))
            url_to_id[source.url] = new_id

    node_map: dict[str, str] = {}
    for old_id in sub.nodes:
        if old_id == sub.root_id:
            continue
        node_map[old_id] = f"{settings.node_prefix}{node_index}"
        node_index += 1

    added_roots: list[str] = []
    for old_id, node in sub.nodes.items():
        if old_id == sub.root_id:
            continue
        payload = node.model_dump(mode="json")
        payload["id"] = node_map[old_id]
        payload["parent_id"] = node_map.get(payload["parent_id"] or "", node_id)
        payload["children"] = [node_map.get(child, child) for child in payload["children"]]
        analysis = payload["analysis"]
        for attr in ("best_practices", "expert_views", "advanced_methods", "existing_tools"):
            for item in analysis.get(attr, []):
                item["source_ids"] = [
                    source_map.get(sid, sid) for sid in item.get("source_ids", [])
                ]
        merged = Node.model_validate(payload)
        run.nodes[merged.id] = merged
        if merged.parent_id == node_id:
            added_roots.append(merged.id)

    target = run.nodes[node_id]
    target.children = list(dict.fromkeys([*target.children, *sorted(added_roots)]))
    if target.stop_reason is not None:
        target.notes.append(f"expandido sob demanda (era {target.stop_reason.value})")
        target.stop_reason = None
    run.learning_path = _post_order(run.nodes, run.root_id)
    return run
