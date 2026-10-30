from __future__ import annotations

import json

import pytest

from abstrator import mcp_server
from abstrator.llm import FakeLLM


@pytest.fixture
def mcp_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ABSTRATOR_LLM_PROVIDER", "fake")
    monkeypatch.setenv("ABSTRATOR_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ABSTRATOR_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("ABSTRATOR_RESPECT_ROBOTS", "false")
    monkeypatch.setenv("ABSTRATOR_RATE_LIMIT_PER_DOMAIN", "0")
    monkeypatch.setenv("ABSTRATOR_SEARXNG_URL", "http://searxng.test")
    from abstrator.config import reset_settings_cache

    reset_settings_cache()
    yield tmp_path
    reset_settings_cache()


def test_cancel_run_reports_unknown_run(mcp_env):
    payload = json.loads(mcp_server.cancel_run("r_inexistente"))
    assert payload["cancelled"] is False


def test_cancel_run_registers_active_runs(mcp_env):
    from abstrator.engine.orchestrator import Orchestrator
    from abstrator.llm import FakeLLM

    orchestrator = Orchestrator(
        mcp_env and _settings_for(mcp_env), FakeLLM(), search=None, fetcher=None
    )
    mcp_server.ACTIVE["r_ativa"] = orchestrator
    payload = json.loads(mcp_server.cancel_run("r_ativa"))

    assert payload["cancelled"] is True
    assert orchestrator.cancel_event.is_set()
    mcp_server.ACTIVE.pop("r_ativa")


def _settings_for(tmp_path):
    from abstrator.config import get_settings

    return get_settings()


async def test_tools_are_registered_with_expected_names():
    tools = {tool.name for tool in await mcp_server.mcp.list_tools()}
    assert {
        "abstract",
        "assess_complexity",
        "research_concept",
        "expand_node",
        "get_run",
        "list_runs",
        "cancel_run",
    } <= tools


async def test_resources_are_registered():
    resources = {str(r.uri) for r in await mcp_server.mcp.list_resources()}
    assert "abstraction://schema" in resources

    templates = {t.uri_template for t in await mcp_server.mcp.list_resource_templates()}
    assert any("abstraction://runs/" in t for t in templates)


async def test_assess_complexity_tool(mcp_env):
    result = await mcp_server.assess_complexity("arquitetura de agentes", "planejar um agente")

    assert "complexity" in result
    assert result["complexity"]["verdict"] in {"complex", "simple"}
    assert "hint" in result


async def test_assess_complexity_rejects_bad_lens(mcp_env):
    with pytest.raises(ValueError, match="lente invalida"):
        await mcp_server._lenses(["nao_existe"])


def test_schema_resource_matches_models():
    data = json.loads(mcp_server.schema_resource())
    assert data["title"] == "Run"


def test_get_run_and_list_runs_on_empty_store(mcp_env):
    assert mcp_server.list_runs() == []
    with pytest.raises(FileNotFoundError):
        mcp_server.get_run("nao_existe")


def test_llm_runner_records_usage(mcp_env, monkeypatch):
    from abstrator.config import get_settings
    from abstrator.engine.budget import BudgetTracker
    from abstrator.engine.llm_runner import LLMRunner

    settings = get_settings()
    budget = BudgetTracker.from_settings(settings, "quick")
    runner = LLMRunner(settings, FakeLLM(), budget)
    assert runner.total_usd == 0.0
    assert budget.llm_calls == 0
