from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from ..models import SourceType

ACADEMIC_HOSTS = (
    "arxiv.org",
    "doi.org",
    "springer.com",
    "sciencedirect.com",
    "acm.org",
    "ieee.org",
    "jstor.org",
    "pubmed.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "semanticscholar.org",
    "openreview.net",
    "ssrn.com",
    "researchgate.net",
    "nature.com",
    "science.org",
    "biorxiv.org",
)

DOCS_HOSTS = (
    "docs.",
    "developer.",
    "learn.microsoft.com",
    "docs.python.org",
    "readthedocs.io",
    "wiki.",
    "developer.mozilla.org",
)

FORUM_HOSTS = (
    "stackoverflow.com",
    "stackexchange.com",
    "reddit.com",
    "quora.com",
    "medium.com",
    "dev.to",
    "news.ycombinator.com",
    "discord.com",
    "github.com",
    "gitlab.com",
)

VENDOR_HOSTS = ("csr.", "news.", "blog.", "vendor.")

NEWS_HOSTS = (
    "nytimes.com",
    "theverge.com",
    "wired.com",
    "arstechnica.com",
    "g1.globo.com",
    "folha.uol.com.br",
    "estadao.com.br",
)


@dataclass(slots=True)
class Credibility:
    type: SourceType
    score: float


def _host(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    return host[4:] if host.startswith("www.") else host


def _matches(host: str, markers: tuple[str, ...]) -> bool:
    return any(marker in host for marker in markers)


def classify(url: str, title: str = "", snippet: str = "") -> Credibility:
    """Tipo + score de credibilidade. Academico/docs > especialista > forum/vendor."""
    host = _host(url)
    lowered = f"{title} {snippet}".lower()
    if _matches(host, ACADEMIC_HOSTS) or "arxiv" in lowered or "doi:" in lowered:
        return Credibility(SourceType.ACADEMIC, 0.92)
    if host.startswith("docs.") or host.startswith("developer.") or _matches(host, DOCS_HOSTS):
        return Credibility(SourceType.OFFICIAL_DOCS, 0.88)
    if host in {"wikipedia.org", "britannica.com"} or host.startswith("pt.wikipedia"):
        return Credibility(SourceType.OTHER, 0.6)
    if _matches(host, FORUM_HOSTS):
        if host.startswith("github.com") or host.startswith("gitlab.com"):
            return Credibility(SourceType.VENDOR, 0.55)
        return Credibility(SourceType.FORUM, 0.45)
    if _matches(host, NEWS_HOSTS):
        return Credibility(SourceType.NEWS, 0.6)
    if _matches(host, VENDOR_HOSTS):
        return Credibility(SourceType.VENDOR, 0.55)
    if any(word in lowered for word in ("best practice", "survey", "state of the art", "survey")):
        return Credibility(SourceType.EXPERT, 0.7)
    return Credibility(SourceType.OTHER, 0.5)
