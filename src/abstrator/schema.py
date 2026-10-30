from __future__ import annotations

import json
from pathlib import Path

from .models import Run

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "abstraction.schema.json"


def build_schema() -> dict:
    return Run.model_json_schema()


def export_schema(path: Path | str | None = None) -> Path:
    target = Path(path) if path else SCHEMA_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build_schema(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


if __name__ == "__main__":  # pragma: no cover
    print(export_schema())
