from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import Settings
from .engine.budget import BudgetTracker
from .llm import build_provider
from .llm.base import LLMError
from .models import ComplexityAssessment
from .search.fetch import Fetcher


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    hint: str = ""

    def to_dict(self) -> dict[str, str | bool]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail, "hint": self.hint}


async def doctor(settings: Settings, *, offline: bool = False) -> list[Check]:
    checks: list[Check] = []
    checks.extend(_check_paths(settings))
    checks.append(_check_docker())
    if not offline:
        checks.append(await _check_searxng(settings))
        checks.append(await _check_llm(settings))
        checks.append(await _check_net(settings))
    return checks


def _check_paths(settings: Settings) -> list[Check]:
    out = []
    for label, path in (
        ("data_dir", Path(settings.data_dir)),
        ("runs_dir", Path(settings.runs_dir)),
    ):
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".abstrator_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            out.append(Check(label, True, str(path)))
        except OSError as exc:
            out.append(Check(label, False, str(path), f"sem permissao de escrita: {exc}"))
    return out


def _check_docker() -> Check:
    if shutil.which("docker"):
        return Check("docker", True, shutil.which("docker") or "", "docker compose up -d searxng")
    return Check(
        "docker",
        False,
        "nao encontrado",
        "necessario para o SearXNG local: docker compose up -d searxng",
    )


async def _check_searxng(settings: Settings) -> Check:
    url = settings.searxng_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(f"{url}/search", params={"q": "test", "format": "json"})
        if resp.status_code != 200:
            return Check(
                "searxng",
                False,
                f"HTTP {resp.status_code}",
                "a instancia responde, mas veja se formats: [html, json] esta no settings.yml",
            )
        data = resp.json()
        n = len(data.get("results", []))
        return Check("searxng", True, f"{url} — {n} resultados para 'test'")
    except httpx.HTTPError as exc:
        return Check(
            "searxng",
            False,
            f"{url} inacessivel ({exc.__class__.__name__})",
            "suba com: docker compose up -d searxng",
        )
    except ValueError:
        return Check(
            "searxng",
            False,
            "resposta sem JSON",
            "no settings.yml do SearXNG: search.formats: [html, json]",
        )


async def _check_llm(settings: Settings) -> Check:
    provider_name = settings.resolved_provider()
    model = settings.gemini_cli_model if provider_name == "gemini_cli" else settings.llm_model
    detail = f"{provider_name} / {model or 'default'}"
    if provider_name == "gemini_cli" and not shutil.which(settings.gemini_cli_command):
        return Check(
            "llm",
            False,
            "binario 'gemini' nao encontrado no PATH",
            "npm i -g @google/gemini-cli  ou  use ABSTRATOR_LLM_PROVIDER=opencode_zen",
        )
    if provider_name == "opencode_zen" and not settings.opencode_api_key:
        return Check(
            "llm",
            False,
            "OPENCODE_API_KEY ausente",
            "pegue a chave em https://opencode.ai/console e coloque no .env",
        )
    try:
        provider = build_provider(settings)
        result = await provider.complete_structured(
            'Classifique a complexidade de "como funciona HTTP" e responda APENAS o JSON '
            'no formato: {"score": <float 0-1>, "verdict": "trivial|simple|moderate|complex", '
            '"reason": "<uma frase>"}',
            ComplexityAssessment,
            stage="doctor",
        )
        await provider.aclose()
        return Check(
            "llm",
            True,
            f"{detail} — ok ({result.value.verdict.value}, {result.usage.output_tokens} tokens)",
        )
    except (LLMError, Exception) as exc:  # noqa: BLE001 - doctor reporta tudo
        return Check("llm", False, f"{detail} — {exc}", "veja abstrator doctor --verbose")


async def _check_net(settings: Settings) -> Check:
    fetcher = Fetcher(settings, BudgetTracker.from_settings(settings, "quick"))
    try:
        result = await fetcher.fetch("https://example.com/")
        return Check(
            "net/robots",
            result.usable,
            f"exemplo.com: status={result.status} chars={len(result.text)}"
            if result.usable
            else f"exemplo.com: {result.blocked_reason or 'sem texto extraido'}",
            "",
        )
    finally:
        await fetcher.aclose()


def ok(checks: list[Check]) -> bool:
    return all(c.ok for c in checks)


def format_checks(checks: list[Check]) -> str:
    lines = []
    for check in checks:
        mark = "OK  " if check.ok else "FALHA"
        lines.append(f"[{mark}] {check.name}: {check.detail}")
        if not check.ok and check.hint:
            lines.append(f"        -> {check.hint}")
    return "\n".join(lines)


def env_summary(settings: Settings) -> str:
    return (
        f"provider={settings.llm_provider}({settings.resolved_provider()}) "
        f"model={settings.llm_model} "
        f"searxng={settings.searxng_url} "
        f"api_key={'sim' if settings.opencode_api_key else 'nao'} "
        f"cwd={os.getcwd()}"
    )
