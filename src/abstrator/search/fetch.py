from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from ..config import Settings
from ..engine.budget import BudgetTracker

log = logging.getLogger(__name__)

BLOCKED_SCHEMES = ("mailto:", "javascript:", "data:", "file:", "ftp:")


@dataclass(slots=True)
class FetchResult:
    url: str
    ok: bool = False
    status: int = 0
    title: str = ""
    text: str = ""
    blocked_reason: str = ""
    from_cache: bool = False

    @property
    def usable(self) -> bool:
        return self.ok and bool(self.text.strip())


@dataclass
class Fetcher:
    """Baixa paginas com guardrails: robots.txt, rate limit por dominio, sem cookies."""

    settings: Settings
    budget: BudgetTracker
    cache: Any | None = None
    audit: Any | None = None
    client: httpx.AsyncClient | None = None
    _last_hit: dict[str, float] = field(default_factory=dict, init=False)
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict, init=False)
    _robots: dict[str, tuple[float, RobotFileParser | None]] = field(
        default_factory=dict, init=False
    )
    _owned_client: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=self.settings.request_timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": self.settings.user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                },
                cookies=httpx.Cookies(),
            )
            self._owned_client = True

    async def aclose(self) -> None:
        if self._owned_client and self.client is not None:
            await self.client.aclose()

    # --- guardrails -------------------------------------------------------- #

    @staticmethod
    def host_of(url: str) -> str:
        return (urlparse(url).netloc or "").lower()

    async def _throttle(self, host: str) -> None:
        interval = max(0.0, self.settings.rate_limit_per_domain)
        if interval <= 0:
            return
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            last = self._last_hit.get(host)
            if last is not None:
                wait = interval - (time.monotonic() - last)
                if wait > 0:
                    await asyncio.sleep(wait)
            self._last_hit[host] = time.monotonic()

    async def _get(self, url: str) -> httpx.Response:
        """GET sem estado: o jar de cookies e sempre limpo (guardrail)."""
        assert self.client is not None
        try:
            response = await self.client.get(url)
        finally:
            if self.client is not None:
                self.client.cookies.clear()
        return response

    async def allowed_by_robots(self, url: str) -> tuple[bool, str]:
        if not self.settings.respect_robots:
            return True, ""
        host = self.host_of(url)
        origin = f"{urlparse(url).scheme}://{host}"
        cached = self._robots.get(host)
        now = time.monotonic()
        if cached and (now - cached[0]) < self.settings.robots_cache_ttl:
            parser = cached[1]
        else:
            parser = await self._load_robots(origin)
            self._robots[host] = (now, parser)
        if parser is None:
            return True, ""
        try:
            ok = parser.can_fetch(self.settings.user_agent, url)
        except Exception:  # robots malformado: nao bloqueia
            return True, ""
        return ok, "" if ok else "robots.txt"

    async def _load_robots(self, origin: str) -> RobotFileParser | None:
        assert self.client is not None
        try:
            await self._throttle(self.host_of(origin))
            resp = await self._get(f"{origin}/robots.txt")
            if resp.status_code >= 400:
                return None
        except httpx.HTTPError as exc:
            log.debug("robots.txt indisponivel em %s: %s", origin, exc)
            return None
        parser = RobotFileParser()
        parser.parse(resp.text.splitlines())
        return parser

    # --- fetch -------------------------------------------------------------- #

    async def fetch(self, url: str, *, use_cache: bool = True) -> FetchResult:
        url = url.strip()
        if url.startswith(BLOCKED_SCHEMES) or not url.startswith(("http://", "https://")):
            return FetchResult(url=url, blocked_reason="esquema nao permitido")

        if self.cache is not None and use_cache:
            cached = await self.cache.get_page(url, self.settings.cache_ttl_hours)
            if cached is not None:
                return FetchResult(
                    url=url,
                    ok=True,
                    title=cached.get("title", ""),
                    text=cached.get("text", ""),
                    from_cache=True,
                )

        ok, reason = await self.allowed_by_robots(url)
        if not ok:
            self._audit("fetch_blocked", url=url, reason=reason)
            return FetchResult(url=url, blocked_reason=reason)

        self.budget.ensure()
        try:
            await self._throttle(self.host_of(url))
            resp = await self._get(url)
        except httpx.HTTPError as exc:
            self._audit("fetch_error", url=url, error=str(exc))
            return FetchResult(url=url, blocked_reason=f"erro de rede: {exc.__class__.__name__}")

        title, text = extract(resp.text, resp.headers.get("content-type", ""))
        self.budget.spend_page()
        self._audit("fetch", url=url, status=resp.status_code, chars=len(text))
        if self.cache is not None and use_cache and text:
            await self.cache.put_page(url, title, text)
        return FetchResult(url=url, ok=True, status=resp.status_code, title=title, text=text)

    def _audit(self, event: str, **fields: Any) -> None:
        if self.audit is not None:
            self.audit.record(event, **fields)


def extract(html: str, content_type: str = "") -> tuple[str, str]:
    """Titulo + texto principal. trafilatura primeiro, strip de tags como reserva."""
    if not html:
        return "", ""
    if content_type and "html" not in content_type.lower() and "text" not in content_type.lower():
        return "", html.strip()
    try:
        import trafilatura

        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            favor_precision=True,
        )
        if extracted:
            try:
                meta = trafilatura.extract_metadata(html)
                title = (meta.title if meta else "") or ""
            except Exception:  # pragma: no cover
                title = ""
            return title, extracted.strip()
    except Exception as exc:  # pragma: no cover - dependencia opcional
        log.debug("trafilatura falhou: %s", exc)
    return "", strip_tags(html)


def strip_tags(html: str) -> str:
    import re

    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return re.sub(r"\s+", " ", text).strip()
