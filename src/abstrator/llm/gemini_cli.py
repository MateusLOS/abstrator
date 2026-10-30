from __future__ import annotations

import asyncio
import json
import os
import shutil

from pydantic import BaseModel

from ..config import Settings
from .base import LLMError, LLMUsage, StructuredMixin


def resolve_command(command: str) -> list[str]:
    """No Windows os shims do npm (.cmd) so rodam via cmd /c."""
    path = shutil.which(command)
    if path and path.rsplit(".", 1)[-1].lower() in {"cmd", "bat"}:
        return [path]
    return [command]


class GeminiCLIProvider(StructuredMixin):
    """Provider que delega ao binario `gemini` (sem chave de API)."""

    def __init__(self, settings: Settings) -> None:
        self.provider_name = "gemini_cli"
        self.model_name = settings.gemini_cli_model or "gemini-cli-default"
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
            *resolve_command(self._settings.gemini_cli_command),
            "-p",
            full,
            "-o",
            "json",
            "--approval-mode",
            "plan",
        ]
        if self._settings.gemini_cli_model:
            argv += ["-m", self._settings.gemini_cli_model]
        stdout, stderr, code = await self._spawn(argv, self._settings.gemini_cli_timeout)
        if code != 0:
            raise LLMError(f"gemini CLI falhou ({code}): {stderr.strip()[:800]}")
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {"response": stdout}
        text = payload.get("response") or payload.get("text") or stdout
        stats = payload.get("stats") or {}
        self._usage = LLMUsage(
            input_tokens=int(stats.get("input_tokens") or max(1, len(full) // 4)),
            output_tokens=int(stats.get("output_tokens") or max(1, len(str(text)) // 4)),
        )
        return str(text)

    async def _spawn(self, argv: list[str], timeout: float) -> tuple[str, str, int]:
        if argv[0].lower().endswith((".cmd", ".bat")):
            argv = ["cmd", "/c", *argv]
        # headless: a pasta nao passa pelo fluxo interativo de "trust"
        env = {**os.environ, "GEMINI_CLI_TRUST_WORKSPACE": "true"}
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError as exc:
            proc.kill()
            raise LLMError(f"gemini CLI excedeu {timeout}s") from exc
        return (
            out.decode("utf-8", "replace"),
            err.decode("utf-8", "replace"),
            proc.returncode or 0,
        )
