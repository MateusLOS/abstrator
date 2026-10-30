from __future__ import annotations

from pathlib import Path

import pytest

from abstrator.config import Settings
from abstrator.llm import FakeLLM
from abstrator.search.fetch import FetchResult
from abstrator.search.searxng import SearchResult


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        searxng_url="http://searxng.test",
        llm_provider="fake",
        llm_model="fake-model",
        data_dir=tmp_path / "data",
        runs_dir=tmp_path / "runs",
        rate_limit_per_domain=0.0,
        respect_robots=False,
        max_pages_per_node=2,
        max_search_results=3,
        budget_max_llm_calls=200,
        budget_max_queries=200,
        budget_max_pages=400,
        cache_ttl_hours=0,
        concept_cache_ttl_hours=0,
    )


@pytest.fixture
def provider() -> FakeLLM:
    return FakeLLM()


class FakeSearch:
    """Busca deterministica: 2 resultados por query, sem rede."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query: str, **kwargs) -> list[SearchResult]:
        self.queries.append(query)
        slug = query.lower().replace(" ", "-")[:40]
        return [
            SearchResult(
                url=f"https://example.org/{slug}-{i}",
                title=f"Resultado {i} para {query}",
                content=f"conteudo relevante sobre {query} ({i})",
                engine="fake",
                score=1.0 - i * 0.1,
            )
            for i in range(2)
        ]

    async def aclose(self) -> None:
        return None


class FakeFetcher:
    def __init__(self) -> None:
        self.fetched: list[str] = []

    async def fetch(self, url: str, **kwargs) -> FetchResult:
        self.fetched.append(url)
        return FetchResult(
            url=url,
            ok=True,
            status=200,
            title=f"titulo de {url}",
            text=(
                f"Texto extraido de {url}. Conceito explicado em detalhe, com exemplos, "
                "numeros e recomendacoes. Fonte util para a lente." * 6
            ),
        )

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_search() -> FakeSearch:
    return FakeSearch()


@pytest.fixture
def fake_fetcher() -> FakeFetcher:
    return FakeFetcher()
