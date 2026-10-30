"""Prompts versionados e editaveis (um arquivo por etapa do pipeline)."""

from __future__ import annotations

import functools
from pathlib import Path

from ..models import Lens
from .lenses_guidance import LENS_GUIDANCE, LENS_SYSTEM

PROMPT_VERSION = "1"
PROMPTS_DIR = Path(__file__).parent


@functools.cache
def load(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"prompt nao encontrado: {path}")
    return path.read_text(encoding="utf-8")


def render(name: str, /, **fields: object) -> str:
    text = load(name)
    missing = {k for k in _placeholders(text) if k not in fields}
    if missing:
        raise KeyError(f"prompt {name} sem os campos: {sorted(missing)}")
    return text.format(**fields)


def _placeholders(text: str) -> set[str]:
    import string

    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


__all__ = ["render", "load", "LENS_GUIDANCE", "LENS_SYSTEM", "PROMPT_VERSION", "Lens"]
