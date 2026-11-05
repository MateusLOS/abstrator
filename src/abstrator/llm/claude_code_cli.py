from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from pathlib import Path

from pydantic import BaseModel

from ..config import Settings
from .base import LLMError, LLMUsage, StructuredMixin

log = logging.getLogger(__name__)

_GLOBAL_SETTINGS = Path.home() / ".claude" / "settings.json"
_hooks_lock = asyncio.Lock()


def resolve_claude(command: str) -> list[str]:
    """No Windows o shim do npm (.cmd) precisa de cmd /c."""
    path = shutil.which(command)
    if path and path.rsplit(".", 1)[-1].lower() in {"cmd", "bat"}:
        return [path]
    return [command]


def _read_hooks() -> dict | None:
    if not _GLOBAL_SETTINGS.exists():
        return None
    try:
        data = json.loads(_GLOBAL_SETTINGS.read_text(encoding="utf-8"))
        h = data.get("hooks")
        return h if h else None
    except Exception as exc:
        log.warning("claude_code_cli: erro lendo settings.json: %s", exc)
        return None


def _write_hooks(hooks: dict) -> None:
    if not _GLOBAL_SETTINGS.exists():
        return
    try:
        data = json.loads(_GLOBAL_SETTINGS.read_text(encoding="utf-8"))
        data["hooks"] = hooks
        _GLOBAL_SETTINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        log.warning("claude_code_cli: erro escrevendo settings.json: %s", exc)


def _extract_json(text: str) -> str | None:
    """Extrai primeiro objeto JSON balanceado do texto. Retorna None se não encontrar."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            escape = not escape and ch == "\\"
            if not escape and ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


class ClaudeCodeCLIProvider(StructuredMixin):
    """Provider que delega ao binário `claude` (Claude Code CLI).

    Usa as credenciais OAuth da assinatura Claude Pro — sem custo de API separado.
    Requer Claude Code instalado: https://claude.ai/code

    Antes de cada chamada desabilita temporariamente os hooks do ai-memory no
    settings.json global (restaura no finally) para evitar contaminação de
    contexto de sessão nas respostas estruturadas JSON.

    Se o modelo retornar Markdown em vez de JSON (comportamento comum via CLI),
    faz uma segunda chamada mínima de conversão Markdown→JSON.
    """

    def __init__(self, settings: Settings) -> None:
        self.provider_name = "claude_code_cli"
        self.model_name = settings.llm_model or "claude-haiku-4-5-20251001"
        self.temperature = settings.llm_temperature
        self.max_attempts = settings.llm_max_retries + 1
        self.pricing = (0.0, 0.0)
        self.usage_log = []
        self._settings = settings
        self._usage = LLMUsage()

    @property
    def _last_usage(self) -> LLMUsage:
        return self._usage

    async def _complete(
        self,
        prompt: str,
        schema: type[BaseModel],
        system: str | None,
        temperature: float | None,
        previous_error: Exception | None,
    ) -> str:
        full = f"{system}\n\n{prompt}" if system else prompt
        argv = [
            *resolve_claude("claude"),
            "-p", full,
            "--output-format", "json",
        ]
        if self.model_name:
            argv += ["--model", self.model_name]

        stdout, stderr, code = await self._spawn_no_hooks(argv, self._settings.llm_timeout)

        if code != 0:
            raise LLMError(f"claude CLI falhou ({code}): {stderr.strip()[:800]}")

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {"result": stdout}

        text = str(payload.get("result") or payload.get("text") or stdout)

        # Tenta extrair JSON direto da resposta
        json_text = _extract_json(text)
        if json_text:
            cost = float(payload.get("total_cost_usd") or payload.get("cost_usd") or 0.0)
            usage = payload.get("usage") or {}
            self._usage = LLMUsage(
                input_tokens=int(usage.get("input_tokens") or max(1, len(full) // 4)),
                output_tokens=int(usage.get("output_tokens") or max(1, len(text) // 4)),
                cost_usd=cost,
            )
            return json_text

        # Fallback: o modelo retornou Markdown — converte para JSON via segunda chamada
        log.info("claude_code_cli: resposta nao e JSON, convertendo Markdown→JSON")
        schema_json = json.dumps(schema.model_json_schema(), indent=2, ensure_ascii=False)
        conversion_prompt = (
            "Converta a análise abaixo para um objeto JSON válido que siga EXATAMENTE este schema.\n"
            "Responda APENAS com o objeto JSON. Sem texto, sem markdown, sem explicação.\n\n"
            f"Schema:\n{schema_json}\n\n"
            f"Análise:\n{text[:3000]}"
        )
        conv_argv = [
            *resolve_claude("claude"),
            "-p", conversion_prompt,
            "--output-format", "json",
        ]
        if self.model_name:
            conv_argv += ["--model", self.model_name]

        conv_stdout, conv_stderr, conv_code = await self._spawn_no_hooks(
            conv_argv, self._settings.llm_timeout
        )
        if conv_code != 0:
            raise LLMError(f"conversão MD→JSON falhou ({conv_code}): {conv_stderr.strip()[:400]}")

        try:
            conv_payload = json.loads(conv_stdout)
        except json.JSONDecodeError:
            conv_payload = {"result": conv_stdout}

        conv_text = str(conv_payload.get("result") or conv_payload.get("text") or conv_stdout)
        json_text = _extract_json(conv_text)
        if not json_text:
            raise LLMError("conversão MD→JSON não retornou JSON válido")

        # Soma o custo das duas chamadas
        cost1 = float(payload.get("total_cost_usd") or 0.0)
        cost2 = float(conv_payload.get("total_cost_usd") or 0.0)
        usage1 = payload.get("usage") or {}
        usage2 = conv_payload.get("usage") or {}
        self._usage = LLMUsage(
            input_tokens=int((usage1.get("input_tokens") or 0) + (usage2.get("input_tokens") or 0)),
            output_tokens=int((usage1.get("output_tokens") or 0) + (usage2.get("output_tokens") or 0)),
            cost_usd=cost1 + cost2,
        )
        return json_text

    async def _spawn_no_hooks(self, argv: list[str], timeout: float) -> tuple[str, str, int]:
        """Executa claude com hooks do ai-memory temporariamente desabilitados."""
        async with _hooks_lock:
            original = _read_hooks()
            if original is not None:
                _write_hooks({})
            try:
                return await self._spawn(argv, timeout)
            finally:
                if original is not None:
                    _write_hooks(original)

    async def _spawn(self, argv: list[str], timeout: float) -> tuple[str, str, int]:
        if argv[0].lower().endswith((".cmd", ".bat")):
            argv = ["cmd", "/c", *argv]
        env = {**os.environ}
        # cwd neutro: evita carregar histórico de sessão do projeto abstrator
        neutral_cwd = str(Path.home())
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=neutral_cwd,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError as exc:
            proc.kill()
            raise LLMError(f"claude CLI excedeu {timeout}s") from exc
        return (
            out.decode("utf-8", "replace"),
            err.decode("utf-8", "replace"),
            proc.returncode or 0,
        )
