from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from ..models import (
    ComplexityAssessment,
    ComplexityVerdict,
    Decomposition,
    Improvements,
    Integration,
    IntentDraft,
    LensFinding,
    RootSynthesis,
    SubKind,
)
from .base import LLMUsage, StructuredMixin

Response = dict[str, Any] | BaseModel | str
Script = Callable[[str, type[BaseModel]], Response]

_SOURCE_ID_RE = re.compile(r"\bs\d+\b")
_COMPLEX_AFTER_RE = re.compile(r"[Pp]rofundidade:\s*(\d+)")


class FakeLLM(StructuredMixin):
    """Provider deterministico para testes: nao faz rede, nao cobra, nao varia.

    Uso:
        FakeLLM()                                        # heuristica estavel
        FakeLLM(script={Decomposition: {"subs": [...]}}) # respostas fixas
        FakeLLM(script=lambda prompt, schema: {...})     # callback
    """

    def __init__(
        self,
        *,
        script: Script | dict[str, Any] | None = None,
        model: str = "fake-model",
        max_complex_calls: int = 3,
    ) -> None:
        self.provider_name = "fake"
        self.model_name = model
        self.temperature = 0.0
        self.max_attempts = 1
        self.pricing = (0.0, 0.0)
        self.usage_log = []
        self.prompts: list[str] = []
        self.calls: list[str] = []
        self._script = script
        self._counts: dict[str, int] = {}
        self.max_complex_calls = max_complex_calls

    @property
    def _last_usage(self) -> LLMUsage:
        return LLMUsage(input_tokens=0, output_tokens=0)

    async def _complete(
        self,
        prompt: str,
        schema: type[BaseModel],
        system: str | None,
        temperature: float | None,
        previous_error: Exception | None,
    ) -> str:
        self.prompts.append(prompt)
        self.calls.append(schema.__name__)
        payload = self._resolve(prompt, schema)
        return payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)

    def _resolve(self, prompt: str, schema: type[BaseModel]) -> Response:
        script = self._script
        if callable(script):
            return script(prompt, schema)
        if isinstance(script, dict):
            entry = script.get(schema.__name__, script.get("*"))
            if isinstance(entry, list) and entry:
                index = self._counts.get(schema.__name__, 0)
                self._counts[schema.__name__] = index + 1
                return entry[min(index, len(entry) - 1)]
            if entry is not None:
                return entry
        return synthesize(prompt, schema, max_complex_calls=self.max_complex_calls)


# --------------------------------------------------------------------------- #
# Gerador heuristico deterministico
# --------------------------------------------------------------------------- #


def _digest(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def _source_ids(prompt: str, limit: int = 2) -> list[str]:
    found = list(dict.fromkeys(_SOURCE_ID_RE.findall(prompt)))
    return found[:limit]


def _concepts(prompt: str, limit: int = 2) -> list[str]:
    match = re.search(r"Conceito:\s*(.+)", prompt)
    root = (match.group(1).strip() if match else "conceito").strip()
    return [f"{root} - parte {i + 1}" for i in range(limit)]


def synthesize(
    prompt: str, schema: type[BaseModel], *, max_complex_calls: int = 3
) -> dict[str, Any]:
    if schema is ComplexityAssessment:
        seen = _COMPLEX_AFTER_RE.search(prompt)
        always_complex = seen is None or int(seen.group(1)) < max_complex_calls
        if always_complex:
            return {
                "score": 0.82,
                "verdict": ComplexityVerdict.COMPLEX.value,
                "reasons": ["multiplos sub-conceitos", "dependencias"],
                "sub_count_hint": 2,
            }
        return {
            "score": 0.2,
            "verdict": ComplexityVerdict.SIMPLE.value,
            "reasons": ["conceito atomico"],
            "sub_count_hint": 0,
        }
    if schema is Decomposition:
        concepts = _concepts(prompt)
        return {
            "subs": [
                {"concept": c, "kind": SubKind.PART.value, "rationale": "parte mais simples"}
                for c in concepts
            ],
            "reasoning": "dividir para conquistar",
        }
    if schema is LensFinding:
        sids = _source_ids(prompt)
        return {
            "summary": f"achados da lente para: {prompt.splitlines()[0][:80]}",
            "claims": [{"text": "achado com fonte", "source_ids": sids}],
            "analogies": ["funciona como uma receita de cozinha"] if "analogia" in prompt else [],
            "expert_views": [
                {"who": "especialista X", "claim": "recomendacao Y", "source_ids": sids}
            ],
            "advanced_methods": [
                {
                    "name": "metodo avancado Z",
                    "when_to_use": "quando o basics nao bastar",
                    "fit_score": 0.7,
                    "source_ids": sids,
                }
            ],
            "tools": [
                {"name": "Ferramenta F", "free": True, "url": "https://exemplo.org", "note": ""}
            ],
            "confidence": 0.7,
            "uncited_claims": [],
        }
    if schema is Integration:
        return {
            "meaning": "significado consolidado",
            "theory": "enquadramento teorico",
            "practice": "aplicacao pratica",
            "fit_to_goal": "serve ao objetivo",
            "consensus": "concordancia entre as fontes",
            "conflicts": [],
            "open_questions": [],
            "confidence": 0.7,
        }
    if schema is RootSynthesis:
        node_ids = list(dict.fromkeys(re.findall(r"\bn\d+\b", prompt)))[:3]
        sids = _source_ids(prompt)
        return {
            "summary": "resumo do run",
            "recommendations": [
                {
                    "text": "comece pelo basico",
                    "node_ids": node_ids[:1],
                    "source_ids": sids,
                    "rationale": "ordem de aprizado",
                }
            ],
            "conflicts": [],
            "open_questions": [],
        }
    if schema is IntentDraft:
        return {"goal": "entender o pedido", "type": "mixed", "constraints": []}
    if schema is Improvements:
        return {
            "proposals": [
                {
                    "title": "reduzir chamadas de LLM",
                    "problem": "custo alto",
                    "proposal": "cachear respostas por schema+prompt",
                    "impact": "high",
                    "effort": "low",
                    "rationale": "evita repeticao",
                }
            ]
        }
    return _from_json_schema(prompt, schema)


def _from_json_schema(prompt: str, schema: type[BaseModel]) -> dict[str, Any]:
    """Preenche qualquer schema a partir do JSON Schema (fallback generico)."""
    js = schema.model_json_schema()
    sids = _source_ids(prompt)
    data = _build(js, js.get("properties", {}), prompt, sids, _digest(prompt))
    return json.loads(schema.model_validate(data).model_dump_json())


def _build(
    js: dict[str, Any],
    props: dict[str, Any],
    prompt: str,
    sids: list[str],
    seed: int,
) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for name, spec in props.items():
        data[name] = _value(name, spec, prompt, sids, seed + _digest(name))
    return data


def _value(name: str, spec: dict[str, Any], prompt: str, sids: list[str], seed: int) -> Any:
    kind = spec.get("type")
    if "enum" in spec:
        return spec["enum"][seed % len(spec["enum"])]
    if kind == "array":
        items = spec.get("items", {"type": "string"})
        count = 1 if seed % 2 == 0 else 2
        if name == "subs":
            count = 2
        return [_value(name, items, prompt, sids, seed + i) for i in range(count)]
    if kind == "object":
        return _build(spec, spec.get("properties", {}), prompt, sids, seed)
    if kind == "integer":
        return 1
    if kind == "number":
        return 0.5
    if kind == "boolean":
        return name == "free" or name == "simpler_than_parent"
    if name == "source_ids":
        return sids
    if name in {"concept", "goal", "summary"}:
        return f"{name} gerado para teste"
    return f"{name} de teste ({seed % 1000})"


__all__ = ["FakeLLM", "synthesize"]
