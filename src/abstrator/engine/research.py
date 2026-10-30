from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..config import IdFactory, Settings
from ..models import Lens, LensFinding, Source, SourceId
from ..prompts import LENS_GUIDANCE, LENS_SYSTEM, render
from ..search.credibility import classify
from ..search.fetch import Fetcher
from ..search.lenses import LENS_SPECS
from ..search.searxng import SearchResult, SearxngClient
from .llm_runner import LLMRunner

log = logging.getLogger(__name__)

MAX_CHARS_PER_SOURCE = 1600
MAX_SNIPPET = 400


@dataclass
class SourceRegistry:
    """Ids estaveis de fonte por URL, com remapeamento para runs diferentes."""

    ids: IdFactory
    sources: dict[str, Source] = field(default_factory=dict)
    by_url: dict[str, str] = field(default_factory=dict)

    def register(self, url: str, title: str = "", snippet: str = "") -> str:
        url = url.strip()
        if url in self.by_url:
            return self.by_url[url]
        sid = self.ids.source()
        cred = classify(url, title, snippet)
        self.sources[sid] = Source(
            url=url,
            title=title,
            type=cred.type,
            credibility=cred.score,
            snippet=snippet[:MAX_SNIPPET],
        )
        self.by_url[url] = sid
        return sid

    def exists(self, url: str) -> bool:
        return url.strip() in self.by_url

    def remap(self, source_ids: list[str], mapping: dict[str, str]) -> list[str]:
        out: list[str] = []
        for sid in source_ids:
            target = mapping.get(sid, sid)
            if target in self.sources and target not in out:
                out.append(target)
        return out

    def absorb(self, other: SourceRegistry, mapping: dict[str, str]) -> None:
        for sid, source in other.sources.items():
            target = mapping.get(sid, sid)
            if target in self.sources:
                continue
            self.sources[target] = source
            self.by_url[source.url] = target


@dataclass
class ResearchResult:
    findings: dict[Lens, LensFinding] = field(default_factory=dict)
    queries: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    pages: int = 0
    lens_errors: dict[str, str] = field(default_factory=dict)


class ResearchEngine:
    def __init__(
        self,
        settings: Settings,
        search: SearxngClient,
        fetcher: Fetcher,
        llm: LLMRunner,
        registry: SourceRegistry,
    ) -> None:
        self.settings = settings
        self.search = search
        self.fetcher = fetcher
        self.llm = llm
        self.registry = registry

    async def research(
        self, concept: str, goal: str, lenses: tuple[Lens, ...], *, node_id: str = ""
    ) -> ResearchResult:
        result = ResearchResult()
        pages_left = self.settings.max_pages_per_node
        for lens in lenses:
            spec = LENS_SPECS.get(lens)
            if spec is None:
                continue
            queries = [t.format(concept=concept) for t in spec.templates][:2]
            candidates: list[SearchResult] = []
            seen: set[str] = set()
            for query in queries:
                result.queries.append(query)
                try:
                    hits = await self.search.search(
                        query,
                        categories=spec.categories,
                        max_results=spec.per_node_results,
                    )
                except Exception as exc:
                    log.warning("busca falhou (%s): %s", query, exc)
                    continue
                for hit in hits:
                    if hit.url in seen:
                        continue
                    seen.add(hit.url)
                    candidates.append(hit)

            candidates.sort(
                key=lambda r: classify(r.url, r.title, r.content).score + r.score * 0.1,
                reverse=True,
            )

            snippets: list[tuple[str, Source, str]] = []
            for hit in candidates:
                if pages_left <= 0:
                    break
                if self.registry.exists(hit.url):
                    continue
                fetched = await self.fetcher.fetch(hit.url)
                result.pages += 1
                pages_left -= 1
                if not fetched.usable:
                    continue
                sid = self.registry.register(
                    hit.url, fetched.title or hit.title, fetched.text[:MAX_SNIPPET]
                )
                if sid not in result.source_ids:
                    result.source_ids.append(sid)
                snippets.append((sid, self.registry.sources[sid], fetched.text))

            if not snippets:
                continue

            try:
                finding = await self._run_lens(concept, goal, lens, snippets)
            except Exception as exc:
                log.warning("lente %s falhou em %s: %s", lens.value, concept, exc)
                result.lens_errors[lens.value] = str(exc)
                continue
            result.findings[lens] = finding
        return result

    async def _run_lens(
        self,
        concept: str,
        goal: str,
        lens: Lens,
        snippets: list[tuple[str, Source, str]],
    ) -> LensFinding:
        source_block = []
        for sid, source, text in snippets:
            source_block.append(
                f"[{sid}] ({source.type.value}, credibilidade {source.credibility:.2f}) "
                f"{source.title} <{source.url}>\n{text[:MAX_CHARS_PER_SOURCE]}"
            )
        prompt = render(
            "lens",
            concept=concept,
            goal=goal or "(nao informado)",
            lens=lens.value,
            lens_label=LENS_SPECS[lens].label,
            lens_guidance=LENS_GUIDANCE.get(
                lens, "Extraia o que as fontes mostram sobre este aspecto."
            ),
            sources="\n\n".join(source_block),
        )
        return await self.llm.run(
            LensFinding,
            stage=f"lens:{lens.value}",
            prompt=prompt,
            system=LENS_SYSTEM,
        )


def merge_sources(result: ResearchResult, registry: SourceRegistry) -> list[SourceId]:
    return [sid for sid in result.source_ids if sid in registry.sources]


def as_dict(result: ResearchResult) -> dict[str, Any]:
    return {
        "queries": result.queries,
        "source_ids": result.source_ids,
        "pages": result.pages,
        "lens_errors": result.lens_errors,
    }
