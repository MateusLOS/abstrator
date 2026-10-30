from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .config import Settings


class AuditLog:
    """Log append-only em runs/<run_id>/audit.jsonl.

    O run_id so existe depois do inicio da execucao, entao registros feitos antes
    ficam em memoria e sao gravados quando `bind(run_id)` e chamado.
    """

    def __init__(self, root: Path, run_id: str | None = None, enabled: bool = True) -> None:
        self.root = Path(root)
        self.run_id = run_id
        self.enabled = enabled
        self.path = self.root / (run_id or "_pending") / "audit.jsonl"
        self.pending: list[dict[str, Any]] = []
        if enabled and run_id:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def bind(self, run_id: str) -> None:
        self.run_id = run_id
        self.path = self.root / run_id / "audit.jsonl"
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending, self.pending = self.pending, []
        if pending:
            self._write(pending)

    def record(self, event: str, **fields: Any) -> dict[str, Any]:
        payload = {
            "ts": dt.datetime.now(dt.UTC).isoformat(),
            "run_id": self.run_id or "",
            "event": event,
            **fields,
        }
        if not self.enabled:
            return payload
        if self.run_id is None:
            self.pending.append(payload)
        else:
            self._write([payload])
        return payload

    def _write(self, payloads: list[dict[str, Any]]) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            for payload in payloads:
                fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    @staticmethod
    def read(run_dir: Path) -> Iterator[dict[str, Any]]:
        path = Path(run_dir) / "audit.jsonl"
        if not path.exists():
            return iter(())

        def gen() -> Iterator[dict[str, Any]]:
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        yield json.loads(line)

        return gen()


def run_dir_for(settings: Settings, run_id: str) -> Path:
    return Path(settings.runs_dir) / run_id
