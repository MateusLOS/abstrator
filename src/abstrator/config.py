from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import ALL_LENSES, INTEGRATION_LENSES, Lens, RunMode

PROJECT_ROOT = Path(__file__).resolve().parents[2]

QuickLenses = (Lens.MEANING, Lens.PRACTICE, Lens.EXISTING_TOOLS)
StandardLenses = INTEGRATION_LENSES


@dataclass(frozen=True)
class ModePreset:
    name: str
    max_depth: int
    max_fanout: int
    lenses: tuple[Lens, ...]
    max_pages_per_node: int
    max_search_results: int
    budget_scale: float = 1.0
    source_target_per_node: int = 6


PRESETS: dict[str, ModePreset] = {
    RunMode.QUICK.value: ModePreset(
        name=RunMode.QUICK.value,
        max_depth=2,
        max_fanout=3,
        lenses=QuickLenses,
        max_pages_per_node=3,
        max_search_results=8,
        budget_scale=0.35,
        source_target_per_node=3,
    ),
    RunMode.STANDARD.value: ModePreset(
        name=RunMode.STANDARD.value,
        max_depth=3,
        max_fanout=4,
        lenses=StandardLenses,
        max_pages_per_node=6,
        max_search_results=12,
        budget_scale=1.0,
        source_target_per_node=6,
    ),
    RunMode.DEEP.value: ModePreset(
        name=RunMode.DEEP.value,
        max_depth=5,
        max_fanout=5,
        lenses=ALL_LENSES,
        max_pages_per_node=10,
        max_search_results=20,
        budget_scale=2.5,
        source_target_per_node=10,
    ),
}


def preset(mode: str) -> ModePreset:
    try:
        return PRESETS[mode]
    except KeyError as exc:
        raise ValueError(f"modo invalido: {mode} (use {', '.join(PRESETS)})") from exc


# Precos em USD por 1M tokens (entrada, saida). Usado so para orcamento.
PRICING: dict[str, tuple[float, float]] = {
    "space-bunny-free": (0.0, 0.0),
    "big-pickle": (0.0, 0.0),
    "cat-jam-free": (0.0, 0.0),
    "exo-free": (0.0, 0.0),
    "mimo-v2.6-flash-free": (0.0, 0.0),
    "nemotron-3-ultra-free": (0.0, 0.0),
    "longcat-2.5-preview-free": (0.0, 0.0),
    "step-5-preview-free": (0.0, 0.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-5-5": (0.1, 0.5),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-opus-4-8": (5.0, 25.0),
    "gemini-3-flash": (0.5, 3.0),
    "gemini-3.1-pro": (2.0, 12.0),
    "deepseek-v4.1-flash": (0.3, 1.2),
    "glm-5.3-flash": (0.15, 0.5),
    "qwen3.8-flash": (0.15, 0.47),
    "kimi-k2.6": (0.95, 4.0),
}
DEFAULT_PRICING = (1.0, 3.0)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ABSTRATOR_",
        extra="ignore",
        populate_by_name=True,
    )

    # --- busca ---
    searxng_url: str = Field(
        default="http://localhost:8080",
        validation_alias=AliasChoices("ABSTRATOR_SEARXNG_URL", "SEARXNG_URL"),
    )
    search_backend: Literal["searxng"] = "searxng"
    user_agent: str = "abstrator/0.1 (+https://github.com/local/abstrator)"
    request_timeout: float = 20.0
    fetch_concurrency: int = 4
    max_pages_per_node: int = 6
    max_search_results: int = 12
    respect_robots: bool = True
    rate_limit_per_domain: float = 1.0
    robots_cache_ttl: int = 3600

    # --- llm ---
    llm_provider: Literal[
        "auto", "opencode_zen", "gemini_cli", "fake", "anthropic", "ollama", "openrouter"
    ] = "opencode_zen"
    llm_model: str = "claude-sonnet-5"
    llm_timeout: float = 120.0
    llm_max_retries: int = 2
    llm_temperature: float = 0.0
    llm_max_output_tokens: int = 8000
    opencode_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ABSTRATOR_OPENCODE_API_KEY", "OPENCODE_API_KEY"),
    )
    opencode_base_url: str = "https://opencode.ai/inference/v1"
    gemini_cli_command: str = "gemini"
    gemini_cli_model: str = ""
    gemini_cli_timeout: float = 300.0

    # --- anthropic ---
    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ABSTRATOR_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
    )
    anthropic_base_url: str = ""

    # --- ollama ---
    ollama_base_url: str = Field(
        default="http://localhost:11434/v1",
        validation_alias=AliasChoices("ABSTRATOR_OLLAMA_BASE_URL", "OLLAMA_BASE_URL"),
    )
    ollama_model: str = Field(
        default="",
        validation_alias=AliasChoices("ABSTRATOR_OLLAMA_MODEL", "OLLAMA_MODEL"),
    )

    # --- openrouter ---
    openrouter_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ABSTRATOR_OPENROUTER_API_KEY", "OPENROUTER_API_KEY"),
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias=AliasChoices("ABSTRATOR_OPENROUTER_BASE_URL", "OPENROUTER_BASE_URL"),
    )

    # --- orcamento (modo standard; os modos escalam) ---
    budget_max_queries: int = 60
    budget_max_pages: int = 120
    budget_max_llm_calls: int = 80
    budget_max_tokens: int = 400_000
    budget_max_seconds: float = 900.0
    budget_max_usd: float = 2.0
    budget_concurrency: int = 4

    # --- storage ---
    data_dir: Path = PROJECT_ROOT / "data"
    runs_dir: Path = PROJECT_ROOT / "runs"
    cache_ttl_hours: int = 72
    concept_cache_ttl_hours: int = 336
    node_prefix: str = "n"
    source_prefix: str = "s"

    # --- limites de recursao ---
    default_max_depth: int | None = None
    default_max_fanout: int | None = None
    max_depth_hard_cap: int = 8

    @property
    def db_path(self) -> Path:
        return self.data_dir / "abstrator.sqlite3"

    def mode(self, name: str) -> ModePreset:
        p = preset(name)
        if self.default_max_depth is not None:
            p = ModePreset(
                name=p.name,
                max_depth=min(self.default_max_depth, self.max_depth_hard_cap),
                max_fanout=self.default_max_fanout or p.max_fanout,
                lenses=p.lenses,
                max_pages_per_node=self.max_pages_per_node or p.max_pages_per_node,
                max_search_results=p.max_search_results,
                budget_scale=p.budget_scale,
                source_target_per_node=p.source_target_per_node,
            )
        return p

    def scaled_budget(self, name: str) -> dict[str, float]:
        scale = preset(name).budget_scale
        return {
            "max_queries": int(self.budget_max_queries * scale),
            "max_pages": int(self.budget_max_pages * scale),
            "max_llm_calls": int(self.budget_max_llm_calls * scale),
            "max_tokens": int(self.budget_max_tokens * scale),
            "max_seconds": self.budget_max_seconds * scale,
            "max_usd": self.budget_max_usd * scale,
        }

    def pricing(self) -> tuple[float, float]:
        return PRICING.get(self.llm_model, DEFAULT_PRICING)

    def resolved_provider(self) -> str:
        if self.llm_provider != "auto":
            return self.llm_provider
        if self.opencode_api_key:
            return "opencode_zen"
        if self.anthropic_api_key:
            return "anthropic"
        if self.openrouter_api_key:
            return "openrouter"
        return "gemini_cli"


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()


@dataclass
class IdFactory:
    """Gerador de ids estaveis (n1, n2, ... / s1, s2, ...) por execucao."""

    node_prefix: str = "n"
    source_prefix: str = "s"
    _n: int = field(default=0, init=False)
    _s: int = field(default=0, init=False)

    def node(self) -> str:
        self._n += 1
        return f"{self.node_prefix}{self._n}"

    def source(self) -> str:
        self._s += 1
        return f"{self.source_prefix}{self._s}"
