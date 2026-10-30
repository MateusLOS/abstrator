from __future__ import annotations

from dataclasses import dataclass

from ..models import Lens


@dataclass(frozen=True)
class LensSpec:
    lens: Lens
    label: str
    categories: str
    templates: tuple[str, ...]
    per_node_results: int


LENS_SPECS: dict[Lens, LensSpec] = {
    Lens.MEANING: LensSpec(
        lens=Lens.MEANING,
        label="significado",
        categories="general",
        templates=("{concept} definicao", "{concept} o que e"),
        per_node_results=6,
    ),
    Lens.ANALOGY: LensSpec(
        lens=Lens.ANALOGY,
        label="analogia",
        categories="general",
        templates=("{concept} analogia", "{concept} parecido com"),
        per_node_results=4,
    ),
    Lens.THEORY: LensSpec(
        lens=Lens.THEORY,
        label="teoria",
        categories="science",
        templates=("{concept} teoria", "{concept} survey"),
        per_node_results=8,
    ),
    Lens.PRACTICE: LensSpec(
        lens=Lens.PRACTICE,
        label="pratica",
        categories="general",
        templates=("{concept} como implementar", "{concept} tutorial passo a passo"),
        per_node_results=8,
    ),
    Lens.BEST_PRACTICES: LensSpec(
        lens=Lens.BEST_PRACTICES,
        label="boas praticas",
        categories="general",
        templates=("{concept} best practices", "{concept} erros comuns"),
        per_node_results=8,
    ),
    Lens.EXPERT_VIEWS: LensSpec(
        lens=Lens.EXPERT_VIEWS,
        label="especialistas",
        categories="science",
        templates=(
            "{concept} specialist opinion expert",
            "{concept} state of the art research",
        ),
        per_node_results=8,
    ),
    Lens.ADVANCED_METHODS: LensSpec(
        lens=Lens.ADVANCED_METHODS,
        label="metodos avancados",
        categories="science",
        templates=("{concept} advanced methods", "{concept} architecture"),
        per_node_results=6,
    ),
    Lens.EXISTING_TOOLS: LensSpec(
        lens=Lens.EXISTING_TOOLS,
        label="ferramentas",
        categories="it",
        templates=(
            "{concept} ferramentas",
            "{concept} library open source",
            "{concept} free alternative",
        ),
        per_node_results=8,
    ),
}


def searxng_categories(lenses: tuple[Lens, ...]) -> str:
    cats = {LENS_SPECS[lens].categories for lens in lenses if lens in LENS_SPECS}
    return ",".join(sorted(cats)) or "general"


def build_queries(concept: str, lenses: tuple[Lens, ...], goal: str = "") -> list[str]:
    """Queries deterministicas para as lentes dadas (nada de LLM aqui)."""
    base = concept.strip()
    seen: set[str] = set()
    queries: list[str] = []
    for lens in lenses:
        spec = LENS_SPECS.get(lens)
        if spec is None:
            continue
        for template in spec.templates:
            q = template.format(concept=base)
            if goal and lens is Lens.PRACTICE:
                q = f"{q} {goal}".strip()
            key = q.lower()
            if key in seen:
                continue
            seen.add(key)
            queries.append(q)
    return queries
