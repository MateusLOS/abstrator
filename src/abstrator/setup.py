"""Wizard interativo de configuração do provider LLM."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import PROJECT_ROOT, reset_settings_cache

console = Console(legacy_windows=False)

ENV_FILE = PROJECT_ROOT / ".env"

PROVIDERS = {
    "claude_code_cli": {
        "label": "Claude Code (OAuth/Pro)",
        "desc": "Usa a assinatura Claude Pro via CLI — sem chave de API",
        "keys": [],
        "check": lambda: shutil.which("claude") is not None,
        "check_msg": "Requer Claude Code instalado: https://claude.ai/code",
    },
    "anthropic": {
        "label": "Claude API (Anthropic)",
        "desc": "API direta da Anthropic — requer chave paga",
        "keys": ["ANTHROPIC_API_KEY"],
        "check": None,
        "check_msg": "Obtenha a chave em: https://console.anthropic.com",
    },
    "openrouter": {
        "label": "OpenRouter",
        "desc": "Acesso a múltiplos modelos via OpenRouter (50 req/dia gratuito)",
        "keys": ["OPENROUTER_API_KEY"],
        "check": None,
        "check_msg": "Obtenha a chave em: https://openrouter.ai/keys",
    },
    "gemini_cli": {
        "label": "Gemini CLI",
        "desc": "Google Gemini via CLI — sem chave (plano gratuito disponível)",
        "keys": [],
        "check": lambda: shutil.which("gemini") is not None,
        "check_msg": "Requer Gemini CLI: https://github.com/google-gemini/gemini-cli",
    },
    "opencode_zen": {
        "label": "OpenCode",
        "desc": "OpenCode local — sem chave de API",
        "keys": [],
        "check": lambda: shutil.which("opencode") is not None,
        "check_msg": "Requer OpenCode instalado: https://opencode.ai",
    },
    "ollama": {
        "label": "Ollama (local)",
        "desc": "Modelos locais via Ollama — 100% offline, sem custo",
        "keys": [],
        "check": lambda: shutil.which("ollama") is not None,
        "check_msg": "Requer Ollama: https://ollama.com — rode: ollama pull qwen2.5:14b",
    },
}

DEFAULT_MODELS = {
    "claude_code_cli": "claude-haiku-4-5-20251001",
    "anthropic": "claude-haiku-4-5-20251001",
    "openrouter": "google/gemma-3-27b-it:free",
    "gemini_cli": "",
    "opencode_zen": "claude-sonnet-5",
    "ollama": "qwen2.5:14b",
}


def show_provider_table(current: str | None = None) -> None:
    table = Table(title="Providers disponíveis", show_header=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Provider")
    table.add_column("Descrição")
    table.add_column("Status", justify="center")

    for i, (key, info) in enumerate(PROVIDERS.items(), 1):
        check = info["check"]
        if check is None:
            status = "[yellow]chave[/]"
        elif check():
            status = "[green]ok[/]"
        else:
            status = "[red]ausente[/]"

        label = f"[bold]{info['label']}[/]"
        if key == current:
            label += " [cyan](atual)[/]"
        table.add_row(str(i), label, info["desc"], status)

    console.print(table)


def _read_env() -> dict[str, str]:
    """Lê o .env atual como dict de key→value, preservando comentários."""
    if not ENV_FILE.exists():
        return {}
    result: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _, v = stripped.partition("=")
            result[k.strip()] = v.strip()
    return result


def _write_env(updates: dict[str, str]) -> None:
    """Atualiza o .env, preservando outras entradas e comentários."""
    lines: list[str] = []
    updated_keys: set[str] = set()

    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k = stripped.split("=", 1)[0].strip()
                if k in updates:
                    lines.append(f"{k}={updates[k]}")
                    updated_keys.add(k)
                    continue
            lines.append(line)

    # Adiciona keys novas que não existiam
    for k, v in updates.items():
        if k not in updated_keys:
            lines.append(f"{k}={v}")

    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _test_provider(provider: str, model: str) -> bool:
    """Testa se o provider responde corretamente."""
    if provider == "claude_code_cli":
        try:
            r = subprocess.run(
                ["claude", "-p", "ping", "--output-format", "json"],
                capture_output=True, timeout=30,
            )
            return r.returncode == 0
        except Exception:
            return False
    if provider == "gemini_cli":
        try:
            r = subprocess.run(["gemini", "--version"], capture_output=True, timeout=10)
            return r.returncode == 0
        except Exception:
            return False
    if provider == "opencode_zen":
        try:
            r = subprocess.run(["opencode", "--version"], capture_output=True, timeout=10)
            return r.returncode == 0
        except Exception:
            return False
    if provider == "ollama":
        try:
            import urllib.request
            urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5)
            return True
        except Exception:
            return False
    # anthropic / openrouter: só valida que a chave foi fornecida
    env = _read_env()
    if provider == "anthropic":
        return bool(env.get("ANTHROPIC_API_KEY"))
    if provider == "openrouter":
        return bool(env.get("OPENROUTER_API_KEY"))
    return False


def run_setup(provider_name: str | None = None, skip_test: bool = False) -> None:
    """Executa o wizard de configuração."""
    console.print(Panel.fit(
        "[bold cyan]Abstrator — Configuração do Provider LLM[/]\n"
        "Escolha o serviço de IA que o abstrator vai usar para pesquisa.",
        border_style="cyan",
    ))

    from .config import get_settings
    try:
        current = get_settings().llm_provider
    except Exception:
        current = None

    show_provider_table(current)
    provider_keys = list(PROVIDERS.keys())

    if provider_name and provider_name in PROVIDERS:
        chosen_key = provider_name
    else:
        choices = ", ".join(f"{i}={k}" for i, k in enumerate(provider_keys, 1))
        raw = typer.prompt(
            f"\nEscolha o provider ({choices})",
            default=current or "claude_code_cli",
        )
        # aceita número ou nome
        if raw.isdigit() and 1 <= int(raw) <= len(provider_keys):
            chosen_key = provider_keys[int(raw) - 1]
        elif raw in PROVIDERS:
            chosen_key = raw
        else:
            console.print(f"[red]Provider inválido: {raw}[/]")
            raise typer.Exit(1)

    info = PROVIDERS[chosen_key]
    console.print(f"\nProvider selecionado: [bold]{info['label']}[/] — {info['desc']}")

    updates: dict[str, str] = {"ABSTRATOR_LLM_PROVIDER": chosen_key}

    # Coleta chaves obrigatórias
    for key in info["keys"]:
        current_val = _read_env().get(key, "")
        masked = f"{current_val[:8]}..." if len(current_val) > 8 else current_val
        prompt_msg = f"{key}"
        if masked:
            prompt_msg += f" [atual: {masked}]"
        else:
            console.print(f"[dim]{info['check_msg']}[/]")
        val = typer.prompt(prompt_msg, default=current_val, hide_input=True)
        if val:
            updates[key] = val

    # Modelo
    default_model = DEFAULT_MODELS.get(chosen_key, "")
    if chosen_key in ("claude_code_cli", "anthropic", "openrouter"):
        model = typer.prompt("Modelo", default=default_model)
        updates["ABSTRATOR_LLM_MODEL"] = model
    elif chosen_key == "ollama":
        model = typer.prompt("Modelo Ollama", default=default_model)
        updates["ABSTRATOR_LLM_MODEL"] = model
        url = typer.prompt("URL do Ollama", default="http://localhost:11434/v1")
        updates["OLLAMA_BASE_URL"] = url

    _write_env(updates)
    reset_settings_cache()
    console.print(f"\n[green]OK[/] .env atualizado com provider [bold]{chosen_key}[/]")

    # Teste de conexão
    if not skip_test and not info["keys"]:  # testa providers sem chave
        console.print("Testando conexão...", end=" ")
        ok = _test_provider(chosen_key, updates.get("ABSTRATOR_LLM_MODEL", ""))
        if ok:
            console.print("[green]ok[/]")
        else:
            console.print(f"[yellow]nao foi possivel verificar[/]")
            console.print(f"[dim]{info['check_msg']}[/]")

    console.print("\n[bold green]Configuração concluída![/]")
    console.print("Use [cyan]abstrator ask 'sua pergunta'[/] para testar.")
