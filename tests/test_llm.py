from __future__ import annotations

import json

import httpx
import pytest
import respx

from abstrator.llm.base import LLMError, extract_json, parse_structured, schema_instruction
from abstrator.llm.fake import FakeLLM
from abstrator.llm.opencode_zen import OpenCodeZenProvider
from abstrator.models import ComplexityAssessment, LensFinding, SourceType


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == '{"a": 1}'
    assert json.loads(extract_json('texto antes {"a": 1} depois')) == {"a": 1}
    assert json.loads(extract_json('```json\n{"a": 1}\n```')) == {"a": 1}
    assert json.loads(extract_json('{"a": "}"}')) == {"a": "}"}
    assert json.loads(extract_json('{"a": {"b": 2}}')) == {"a": {"b": 2}}
    with pytest.raises(LLMError):
        extract_json("sem json aqui")


def test_parse_structured_validates_and_repairs():
    respostas = ['{"score": 0.9, "verdict": "complex"}', '{"score": 0.9, "verdict": "complex"}']

    def repair(error: str, raw: str) -> str:
        return respostas.pop(0)

    value, attempts = parse_structured(
        '{"score": 9, "verdict": "complexo"}',
        ComplexityAssessment,
        repair=repair,
    )
    assert attempts == 2
    assert value.verdict.value == "complex"


def test_parse_structured_gives_up():
    with pytest.raises(LLMError):
        parse_structured("nao e json", ComplexityAssessment)


def test_schema_instruction_mentions_schema():
    instruction = schema_instruction(ComplexityAssessment)
    assert "JSON Schema" in instruction
    assert "verdict" in instruction


async def test_fake_llm_is_deterministic_and_valid():
    llm = FakeLLM()
    first = await llm.complete_structured("Conceito: x", ComplexityAssessment)
    second = await llm.complete_structured("Conceito: x", ComplexityAssessment)

    assert first.value == second.value
    assert isinstance(first.value, ComplexityAssessment)


async def test_fake_llm_uses_cited_source_ids_from_prompt():
    llm = FakeLLM()
    prompt = "Conceito: x\nFontes:\n[s1] ...\n[s2] ..."
    result = await llm.complete_structured(prompt, LensFinding)
    assert result.value.claims[0].source_ids
    assert set(result.value.claims[0].source_ids) <= {"s1", "s2"}


@respx.mock
async def test_opencode_zen_calls_chat_completions(settings):
    settings.opencode_api_key = "sk-test"
    settings.opencode_base_url = "https://opencode.ai/inference/v1"
    route = respx.post("https://opencode.ai/inference/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"score": 0.4, "verdict": "simple"}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
        )
    )
    provider = OpenCodeZenProvider(settings)
    result = await provider.complete_structured("Conceito: x", ComplexityAssessment)

    body = json.loads(route.calls[0].request.content)
    assert body["model"] == settings.llm_model
    assert body["response_format"]["json_schema"]["name"] == "ComplexityAssessment"
    assert result.usage.input_tokens == 100
    assert result.usage.cost_usd > 0
    await provider.aclose()


@respx.mock
async def test_opencode_zen_falls_back_when_schema_format_rejected(settings):
    settings.opencode_api_key = "sk-test"
    route = respx.post("https://opencode.ai/inference/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(400, json={"error": "response_format not supported"}),
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"score": 0.1, "verdict": "simple"}'}}]},
            ),
        ]
    )
    provider = OpenCodeZenProvider(settings)
    result = await provider.complete_structured("Conceito: x", ComplexityAssessment)

    assert result.value.verdict.value == "simple"
    assert route.call_count == 2
    assert "response_format" not in json.loads(route.calls[1].request.content)
    await provider.aclose()


@respx.mock
async def test_opencode_zen_reports_rate_limit(settings):
    settings.opencode_api_key = "sk-test"
    respx.post("https://opencode.ai/inference/v1/chat/completions").mock(
        return_value=httpx.Response(429, json={"error": "slow down"})
    )
    provider = OpenCodeZenProvider(settings)
    with pytest.raises(LLMError, match="rate limit"):
        await provider.complete_structured("Conceito: x", ComplexityAssessment)
    await provider.aclose()


def test_opencode_zen_requires_api_key(settings):
    settings.opencode_api_key = ""
    with pytest.raises(LLMError, match="OPENCODE_API_KEY"):
        OpenCodeZenProvider(settings)


async def test_gemini_cli_adapter_parses_json_output(settings, monkeypatch):
    from abstrator.llm.gemini_cli import GeminiCLIProvider

    provider = GeminiCLIProvider(settings)
    captured: dict = {}

    async def fake_spawn(argv, timeout):
        captured["argv"] = argv
        return (
            json.dumps({"response": '{"score": 0.6, "verdict": "complex", "reasons": []}'}),
            "",
            0,
        )

    monkeypatch.setattr(provider, "_spawn", fake_spawn)
    result = await provider.complete_structured("Conceito: x", ComplexityAssessment)

    assert result.value.score == 0.6
    assert "-o" in captured["argv"]
    assert "json" in captured["argv"]
    assert result.usage.cost_usd == 0.0


async def test_gemini_cli_adapter_reports_failure(settings, monkeypatch):
    from abstrator.llm.gemini_cli import GeminiCLIProvider

    provider = GeminiCLIProvider(settings)

    async def fake_spawn(argv, timeout):
        return ("", "erro interno", 1)

    monkeypatch.setattr(provider, "_spawn", fake_spawn)
    with pytest.raises(LLMError, match="gemini CLI falhou"):
        await provider.complete_structured("Conceito: x", ComplexityAssessment)


def test_source_types_are_strings():
    assert SourceType.ACADEMIC == "academic"
    assert json.loads(json.dumps({"t": SourceType.FORUM}))["t"] == "forum"
