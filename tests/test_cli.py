from __future__ import annotations

import json

import httpx
import respx
from typer.testing import CliRunner

from abstrator import cli

runner = CliRunner()

SEARCH_PAYLOAD = {
    "results": [
        {
            "url": "https://exemplo.org/a",
            "title": "Artigo sobre viagens",
            "content": "conteudo",
            "engines": ["google"],
            "score": 3.0,
        }
    ]
}


def _env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ABSTRATOR_LLM_PROVIDER", "fake")
    monkeypatch.setenv("ABSTRATOR_LLM_MODEL", "fake-model")
    monkeypatch.setenv("ABSTRATOR_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ABSTRATOR_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("ABSTRATOR_SEARXNG_URL", "http://searxng.test")
    monkeypatch.setenv("ABSTRATOR_RESPECT_ROBOTS", "false")
    monkeypatch.setenv("ABSTRATOR_RATE_LIMIT_PER_DOMAIN", "0")
    from abstrator.config import reset_settings_cache

    reset_settings_cache()


def _mock_web():
    search = respx.get("http://searxng.test/search").mock(
        return_value=httpx.Response(200, json=SEARCH_PAYLOAD)
    )
    page = respx.get(url__startswith="https://exemplo.org").mock(
        return_value=httpx.Response(
            200,
            text="<html><body><article><p>Texto sobre viagens e searched flights, "
            "com detalhes de APIs eFrameworks.</p></article></body></html>",
        )
    )
    return search, page


def test_cli_help():
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    for command in ("run", "expand", "runs", "improve", "mcp", "doctor", "schema"):
        assert command in result.stdout


def test_cli_run_json(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    with respx.mock:
        _mock_web()
        result = runner.invoke(
            cli.app,
            [
                "run",
                "app de busca de viagens",
                "--mode",
                "quick",
                "--format",
                "json",
                "--max-depth",
                "1",
            ],
        )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout[result.stdout.index("{") : result.stdout.rindex("}") + 1])
    assert payload["query"] == "app de busca de viagens"
    assert payload["root_id"] in payload["nodes"]


@respx.mock
def test_cli_run_saves_run_and_report(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    _mock_web()
    result = runner.invoke(
        cli.app, ["run", "cache de respostas", "--mode", "quick", "--max-depth", "0"]
    )

    assert result.exit_code == 0, result.stdout
    runs_dir = tmp_path / "runs"
    saved = list(runs_dir.iterdir())
    assert len(saved) == 1
    assert (saved[0] / "result.json").exists()
    assert (saved[0] / "report.md").exists()
    assert (saved[0] / "audit.jsonl").exists()

    listed = runner.invoke(cli.app, ["runs"])
    assert "cache de respostas" in listed.stdout


@respx.mock
def test_cli_doctor_offline(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, ["doctor", "--offline"])
    assert "data_dir" in result.stdout
    assert "runs_dir" in result.stdout


def test_cli_schema(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    out = tmp_path / "schema.json"
    result = runner.invoke(cli.app, ["schema", "--out", str(out)])
    assert result.exit_code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["title"] == "Run"


@respx.mock
def test_cli_expand(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    _mock_web()
    runner.invoke(cli.app, ["run", "expandir isto", "--mode", "quick", "--max-depth", "0"])
    runs_dir = tmp_path / "runs"
    run_id = list(runs_dir.iterdir())[0].name

    result = runner.invoke(
        cli.app, ["expand", run_id, "n1", "--extra-depth", "1", "--mode", "quick"]
    )
    assert result.exit_code == 0, result.stdout

    updated = json.loads((runs_dir / run_id / "result.json").read_text(encoding="utf-8"))
    assert len(updated["nodes"]) >= 2
