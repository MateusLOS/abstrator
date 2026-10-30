from __future__ import annotations

import difflib

from ..models import Decomposition, SubConcept
from ..prompts import render
from .llm_runner import LLMRunner


def normalize(concept: str) -> str:
    low = concept.lower().strip()
    for filler in ("o ", "a ", "os ", "as ", "de ", "do ", "da ", "como ", "o que e "):
        if low.startswith(filler):
            low = low[len(filler) :]
    return " ".join(low.split())


def _same_word(a: str, b: str) -> bool:
    """Duas palavras contam como a mesma se so mudam de forma (viagem/viajens)."""
    if a == b:
        return True
    if min(len(a), len(b)) < 4:
        return False
    if a.startswith(b) or b.startswith(a):
        return True  # cache/cached
    if min(len(a), len(b)) >= 5 and a[:5] == b[:5]:
        return True  # viagem/viajens (raiz comum), index/indexacao
    if min(len(a), len(b)) < 5:
        return False
    prefix = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    if prefix >= 6:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


def _overlap(tokens_a: set[str], tokens_b: set[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    remaining = set(tokens_b)
    matched = 0
    for token in tokens_a:
        for other in list(remaining):
            if _same_word(token, other):
                matched += 1
                remaining.discard(other)
                break
    return matched / len(tokens_a | tokens_b)


def similarity(a: str, b: str) -> float:
    """0 = conceitos distintos, 1 = mesmo conceito.

    Jaccard de tokens (tolerante a flexao) ignora que 'camada A' e 'camada B' diferem
    so numa letra, enquanto 'viagens' e 'viagem' continuam sendo o mesmo conceito.
    """
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return _overlap(set(na.split()), set(nb.split()))


DUPLICATE_THRESHOLD = 0.7


async def decompose(
    runner: LLMRunner,
    concept: str,
    goal: str,
    depth: int,
    fanout: int,
) -> list[SubConcept]:
    prompt = render(
        "decompose",
        concept=concept,
        goal=goal or "(nao informado)",
        depth=depth,
        count=fanout,
    )
    result: Decomposition = await runner.run(Decomposition, stage="decompose", prompt=prompt)
    return dedupe(result.subs, concept, fanout)


def dedupe(subs: list[SubConcept], parent: str, fanout: int) -> list[SubConcept]:
    """Remove repetidos, quase-iguais do pai e sub-conceitos redundantes entre si."""
    kept: list[SubConcept] = []
    for sub in subs:
        concept = sub.concept.strip()
        if not concept:
            continue
        if similarity(concept, parent) >= DUPLICATE_THRESHOLD:
            continue
        if any(similarity(concept, k.concept) >= DUPLICATE_THRESHOLD for k in kept):
            continue
        kept.append(sub.model_copy(update={"concept": concept}))
        if len(kept) >= fanout:
            break
    return kept
