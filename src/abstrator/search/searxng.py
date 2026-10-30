from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import Settings
from ..engine.budget import BudgetTracker

log = logging.getLogger(__name__)


class SearxngError(RuntimeError):
    pass


@dataclass(slots=True)
class SearchResult:
    url: str
    title: str = ""
    content: str = ""
    engine: str = ""
    category: str = ""
    score: float = 0.0
    published_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "engine": self.engine,
            "category": self.category,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SearchResult:
        return cls(**{k: v for k, v in data.items() if k in cls.__slots__})


@dataclass
class SearxngClient:
    settings: Settings
    budget: BudgetTracker
    client: httpx.AsyncClient | None = None
    cache: Any | None = None
    audit: Any | None = None
    _owned_client: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.settings.searxng_url.rstrip("/"),
                timeout=self.settings.request_timeout,
                headers={"User-Agent": self.settings.user_agent, "Accept": "application/json"},
                cookies=httpx.Cookies(),
            )
            self._owned_client = True

    async def aclose(self) -> None:
        if self._owned_client and self.client is not None:
            await self.client.aclose()

    async def search(
        self,
        query: str,
        *,
        categories: str = "general",
        engines: tuple[str, ...] = (),
        language: str = "",
        max_results: int | None = None,
        use_cache: bool = True,
    ) -> list[SearchResult]:
        assert self.client is not None
        limit = max_results or self.settings.max_search_results
        if self.cache is not None and use_cache:
            cached = await self.cache.get_search(query, categories, self.settings.cache_ttl_hours)
            if cached is not None:
                self._audit("search_cache_hit", query=query, categories=categories, n=len(cached))
                return [SearchResult.from_dict(r) for r in cached][:limit]

        self.budget.ensure()
        params: dict[str, str] = {"q": query, "format": "json", "safesearch": "1"}
        if engines:
            params["engines"] = ",".join(engines)
        else:
            params["categories"] = categories
        if language:
            params["language"] = language
        resp = await self.client.get("/search", params=params)
        if resp.status_code != 200:
            raise SearxngError(f"SearXNG {resp.status_code} para {query!r}: {resp.text[:200]}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise SearxngError(
                "SearXNG nao devolveu JSON (o formato json esta desabilitado no settings.yml?)"
            ) from exc

        results = self._parse(data)
        self.budget.spend_query()
        self._audit("search", query=query, categories=categories, n=len(results))
        if self.cache is not None and use_cache:
            await self.cache.put_search(query, categories, [r.to_dict() for r in results])
        return results[:limit]

    @staticmethod
    def _parse(data: dict[str, Any]) -> list[SearchResult]:
        out: list[SearchResult] = []
        seen: set[str] = set()
        for item in data.get("results", []) or []:
            url = (item.get("url") or "").strip()
            if not url or url in seen:
                continue
            if not url.startswith(("http://", "https://")):
                continue
            seen.add(url)
            engines = item.get("engines") or ([item["engine"]] if item.get("engine") else [])
            out.append(
                SearchResult(
                    url=url,
                    title=(item.get("title") or "").strip(),
                    content=(item.get("content") or "").strip(),
                    engine=str(engines[0]) if engines else "",
                    category=str(item.get("category") or ""),
                    score=float(item.get("score") or 0.0),
                    published_at=str(item.get("publishedDate") or ""),
                )
            )
        return out

    def _audit(self, event: str, **fields: Any) -> None:
        if self.audit is not None:
            self.audit.record(event, **fields)


def is_searxng_json_enabled(url: str) -> bool:
    return urlparse(url).scheme in {"http", "https"}
