from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS search_cache (
    key TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS page_cache (
    key TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS concept_cache (
    key TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    payload TEXT NOT NULL
);
"""


def _now() -> float:
    return time.time()


@dataclass
class CachedSearch:
    results: list[dict[str, Any]]
    hits: int = 0


class Cache:
    """Cache SQLite (search, paginas, conceitos, LLM) com TTL."""

    def __init__(self, path: Path, *, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled
        self._lock = asyncio.Lock()
        self._conn: sqlite3.Connection | None = None
        if enabled:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # --- helpers ---------------------------------------------------------- #

    @staticmethod
    def key(*parts: str) -> str:
        joined = "\x1f".join(p.strip().lower() for p in parts)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def _get(self, table: str, key: str, ttl: float) -> Any | None:
        if not self._conn:
            return None
        row = self._conn.execute(
            f"SELECT created_at, payload FROM {table} WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        if ttl and (_now() - row["created_at"]) > ttl:
            self._conn.execute(f"DELETE FROM {table} WHERE key = ?", (key,))
            self._conn.commit()
            return None
        return json.loads(row["payload"])

    def _put(self, table: str, key: str, payload: Any) -> None:
        if not self._conn:
            return
        self._conn.execute(
            f"INSERT OR REPLACE INTO {table} (key, created_at, payload) VALUES (?, ?, ?)",
            (key, _now(), json.dumps(payload, ensure_ascii=False, default=str)),
        )
        self._conn.commit()

    # --- search ------------------------------------------------------------ #

    async def get_search(
        self, query: str, categories: str, ttl_hours: float
    ) -> list[dict[str, Any]] | None:
        async with self._lock:
            return self._get("search_cache", self.key(query, categories), ttl_hours * 3600)

    async def put_search(self, query: str, categories: str, results: list[dict[str, Any]]) -> None:
        async with self._lock:
            self._put("search_cache", self.key(query, categories), results)

    # --- paginas ----------------------------------------------------------- #

    async def get_page(self, url: str, ttl_hours: float) -> dict[str, Any] | None:
        async with self._lock:
            return self._get("page_cache", url, ttl_hours * 3600)

    async def put_page(self, url: str, title: str, text: str) -> None:
        async with self._lock:
            self._put("page_cache", url, {"title": title, "text": text})

    # --- conceitos --------------------------------------------------------- #

    async def get_concept(self, concept: str, goal: str, ttl_hours: float) -> dict[str, Any] | None:
        async with self._lock:
            return self._get("concept_cache", self.key(concept, goal), ttl_hours * 3600)

    async def put_concept(self, concept: str, goal: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            self._put("concept_cache", self.key(concept, goal), payload)

    # --- llm --------------------------------------------------------------- #

    async def get_llm(
        self, prompt: str, schema_name: str, ttl_hours: float
    ) -> dict[str, Any] | None:
        async with self._lock:
            return self._get("llm_cache", self.key(schema_name, prompt), ttl_hours * 3600)

    async def put_llm(self, prompt: str, schema_name: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            self._put("llm_cache", self.key(schema_name, prompt), payload)
