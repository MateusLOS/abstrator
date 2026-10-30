from __future__ import annotations

from ..models import Complexity, ComplexityAssessment, ComplexityVerdict
from ..prompts import render
from .llm_runner import LLMRunner

# Heuristica barata antes de gastar LLM (opcional, so com settings.use_heuristic_first)
_COMPLEX_HINTS = (
    "arquitetura",
    "orquestra",
    "pipeline",
    "distribuid",
    "escal",
    "seguranca",
    "otimizacao",
    "sistema",
    "framework",
    "plataforma",
)


def heuristic(concept: str) -> Complexity | None:
    low = concept.lower()
    hits = [h for h in _COMPLEX_HINTS if h in low]
    if not hits:
        return None
    return Complexity(
        score=min(0.5 + 0.1 * len(hits), 0.95),
        verdict=ComplexityVerdict.COMPLEX,
        reasons=[f"palavra-chave complexa: {h}" for h in hits],
    )


async def assess_complexity(
    runner: LLMRunner, concept: str, goal: str = "", depth: int = 0
) -> Complexity:
    prompt = render(
        "complexity",
        concept=concept,
        goal=goal or "(nao informado)",
        depth=depth,
    )
    assessment: ComplexityAssessment = await runner.run(
        ComplexityAssessment, stage="complexity", prompt=prompt
    )
    return Complexity(
        score=assessment.score,
        verdict=assessment.verdict,
        reasons=assessment.reasons,
    )
