from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .config import Settings
from .models import Run, RunMeta
from .render.markdown import render_markdown


def run_dir(settings: Settings, run_id: str) -> Path:
    return Path(settings.runs_dir) / run_id


def save_run(settings: Settings, run: Run, *, markdown: bool = True) -> Path:
    """Auto-documentacao: result.json (fonte de verdade) + report.md (leitura humana)."""
    run.validate_tree()
    directory = run_dir(settings, run.run_id)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "result.json"
    json_path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    if markdown:
        (directory / "report.md").write_text(render_markdown(run), encoding="utf-8")
    return json_path


def load_run(settings: Settings, run_id: str) -> Run:
    path = run_dir(settings, run_id) / "result.json"
    if not path.exists():
        raise FileNotFoundError(f"run nao encontrado: {run_id}")
    return Run.model_validate_json(path.read_text(encoding="utf-8"))


def load_run_from_path(path: Path) -> Run:
    return Run.model_validate_json(path.read_text(encoding="utf-8"))


def list_runs(settings: Settings, limit: int = 50) -> list[RunMeta]:
    root = Path(settings.runs_dir)
    if not root.exists():
        return []
    metas: list[RunMeta] = []
    for child in sorted(root.iterdir(), reverse=True):
        result = child / "result.json"
        if not result.exists():
            continue
        try:
            data = json.loads(result.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        budget = data.get("budget") or {}
        metas.append(
            RunMeta(
                run_id=data.get("run_id", child.name),
                query=data.get("query", ""),
                mode=data.get("mode", "standard"),
                created_at=data.get("created_at")
                or dt.datetime.fromtimestamp(
                    child.stat().st_mtime, tz=dt.timezone.utc
                ).isoformat(),
                summary=data.get("summary", ""),
                nodes=len(data.get("nodes") or {}),
                sources=len(data.get("sources") or {}),
                stopped_by=budget.get("stopped_by"),
            )
        )
        if len(metas) >= limit:
            break
    return metas


def run_id_prefix(run_id: str) -> str:
    return run_id.split("_", 1)[-1] if "_" in run_id else run_id


def resolve_run_id(settings: Settings, prefix: str) -> str:
    """Aceita run_id completo ou prefixo (r_2026...)."""
    root = Path(settings.runs_dir)
    direct = run_dir(settings, prefix)
    if (direct / "result.json").exists():
        return prefix
    if root.exists():
        matches = sorted(
            p.name for p in root.iterdir() if p.name.endswith(prefix) or prefix in p.name
        )
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"prefixo ambiguo {prefix!r}: {', '.join(matches)}")
    raise FileNotFoundError(f"run nao encontrado: {prefix}")
