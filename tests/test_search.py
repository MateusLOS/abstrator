from __future__ import annotations

import time

import httpx
import pytest
import respx

from abstrator.engine.budget import BudgetTracker
from abstrator.search.cache import Cache
from abstrator.search.fetch import Fetcher
from abstrator.search.searxng import SearxngClient, SearxngError

SEARCH_PAYLOAD = {
    "results": [
        {
            "url": "https://a.org/1",
            "title": "A",
            "content": "sobre o tema",
            "engines": ["google"],
            "score": 2.0,
        },
        {"url": "https://a.org/1", "title": "A duplicado", "content": "", "engines": ["bing"]},
        {"url": "https://b.org/2", "title": "B", "content": "outro texto"},
        {"url": "javascript:void(0)", "title": "lixo"},
        {"url": "ftp://c.org/3", "title": "lixo"},
    ]
}


def _budget(**kwargs) -> BudgetTracker:
    base = dict(
        max_queries=50,
        max_pages=50,
        max_llm_calls=50,
        max_tokens=10**6,
        max_seconds=60.0,
        max_usd=5.0,
    )
    base.update(kwargs)
    return BudgetTracker(**base)


@respx.mock
async def test_searxng_parses_and_deduplicates(settings):
    route = respx.get("http://searxng.test/search").mock(
        return_value=httpx.Response(200, json=SEARCH_PAYLOAD)
    )
    client = SearxngClient(settings, _budget())
    results = await client.search("viagens", categories="general")

    urls = [r.url for r in results]
    assert urls == ["https://a.org/1", "https://b.org/2"]
    assert route.calls[0].request.url.params["format"] == "json"
    await client.aclose()


@respx.mock
async def test_searxng_uses_engines_when_given(settings):
    route = respx.get("http://searxng.test/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    client = SearxngClient(settings, _budget())
    await client.search("x", engines=("arxiv", "google scholar"))
    assert route.calls[0].request.url.params["engines"] == "arxiv,google scholar"
    await client.aclose()


@respx.mock
async def test_searxng_cache_avoids_second_query(settings, tmp_path):
    route = respx.get("http://searxng.test/search").mock(
        return_value=httpx.Response(200, json=SEARCH_PAYLOAD)
    )
    cache = Cache(tmp_path / "c.sqlite3")
    budget = _budget()
    client = SearxngClient(settings, budget, cache=cache)
    first = await client.search("viagens")
    second = await client.search("viagens")

    assert len(first) == len(second) == 2
    assert route.call_count == 1
    assert budget.queries == 1
    cache.close()
    await client.aclose()


@respx.mock
async def test_searxng_reports_non_json(settings):
    respx.get("http://searxng.test/search").mock(return_value=httpx.Response(200, text="<html>"))
    client = SearxngClient(settings, _budget())
    with pytest.raises(SearxngError, match="json"):
        await client.search("x")
    await client.aclose()


@respx.mock
async def test_fetch_blocks_url_when_robots_disallows(settings):
    robots = respx.get("https://bloqueado.test/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /privado")
    )
    page = respx.get("https://bloqueado.test/privado/x").mock(
        return_value=httpx.Response(200, text="<html>segredo</html>")
    )
    settings.respect_robots = True
    fetcher = Fetcher(settings, _budget())
    result = await fetcher.fetch("https://bloqueado.test/privado/x")

    assert result.blocked_reason == "robots.txt"
    assert not result.ok
    assert robots.call_count == 1
    assert page.call_count == 0
    await fetcher.aclose()


@respx.mock
async def test_fetch_allows_when_robots_permits(settings):
    respx.get("https://livre.test/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /privado")
    )
    respx.get("https://livre.test/publico").mock(
        return_value=httpx.Response(200, text="<html><body><p>ola mundo</p></body></html>")
    )
    settings.respect_robots = True
    fetcher = Fetcher(settings, _budget())
    result = await fetcher.fetch("https://livre.test/publico")

    assert result.ok
    assert "ola" in result.text
    await fetcher.aclose()


@respx.mock
async def test_fetch_rejects_non_http_schemes(settings):
    fetcher = Fetcher(settings, _budget())
    for url in ("mailto:a@b.c", "file:///c:/x", "ftp://x/y"):
        assert (await fetcher.fetch(url)).blocked_reason == "esquema nao permitido"
    await fetcher.aclose()


@respx.mock
async def test_rate_limit_is_respected_per_domain(settings):
    settings.rate_limit_per_domain = 0.4
    respx.get("https://lento.test/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /")
    )
    respx.get("https://lento.test/a").mock(return_value=httpx.Response(200, text="<html>a</html>"))
    respx.get("https://lento.test/b").mock(return_value=httpx.Response(200, text="<html>b</html>"))
    settings.respect_robots = False
    fetcher = Fetcher(settings, _budget())

    start = time.monotonic()
    await fetcher.fetch("https://lento.test/a")
    await fetcher.fetch("https://lento.test/b")
    elapsed = time.monotonic() - start

    assert elapsed >= 0.4
    await fetcher.aclose()


@respx.mock
async def test_no_cookies_are_ever_sent(settings):
    respx.get("https://cookie.test/robots.txt").mock(
        return_value=httpx.Response(
            200, text="User-agent: *\nAllow: /", headers={"Set-Cookie": "sessao=abc; Path=/"}
        )
    )
    page = respx.get("https://cookie.test/pagina").mock(
        return_value=httpx.Response(
            200,
            text="<html>conteudo</html>",
            headers={"Set-Cookie": "sessao=def; Path=/"},
        )
    )
    settings.respect_robots = True
    fetcher = Fetcher(settings, _budget())
    await fetcher.fetch("https://cookie.test/pagina")

    for call in page.calls:
        assert "cookie" not in {k.lower() for k in call.request.headers}
    assert not fetcher.client.cookies
    await fetcher.aclose()


@respx.mock
async def test_fetch_uses_cache_and_counts_pages_once(settings, tmp_path):
    respx.get("https://cache.test/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /")
    )
    page = respx.get("https://cache.test/p").mock(
        return_value=httpx.Response(200, text="<html><p>texto</p></html>")
    )
    settings.respect_robots = True
    cache = Cache(tmp_path / "c.sqlite3")
    budget = _budget()
    fetcher = Fetcher(settings, budget, cache=cache)

    await fetcher.fetch("https://cache.test/p")
    second = await fetcher.fetch("https://cache.test/p")

    assert second.from_cache
    assert page.call_count == 1
    assert budget.pages == 1
    cache.close()
    await fetcher.aclose()


@respx.mock
async def test_fetch_failure_is_reported_not_raised(settings):
    respx.get("https://erro.test/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /")
    )
    respx.get("https://erro.test/p").mock(side_effect=httpx.ConnectError("sem rede"))
    settings.respect_robots = True
    fetcher = Fetcher(settings, _budget())
    result = await fetcher.fetch("https://erro.test/p")

    assert not result.ok
    assert "erro de rede" in result.blocked_reason
    await fetcher.aclose()
