from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

NodeId = Annotated[str, Field(pattern=r"^n\d+$")]
SourceId = Annotated[str, Field(pattern=r"^s\d+$")]


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #


class RunMode(StrEnum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class IntentType(StrEnum):
    PRACTICAL = "practical"
    THEORETICAL = "theoretical"
    MIXED = "mixed"


class Lens(StrEnum):
    MEANING = "meaning"
    ANALOGY = "analogy"
    THEORY = "theory"
    PRACTICE = "practice"
    BEST_PRACTICES = "best_practices"
    EXPERT_VIEWS = "expert_views"
    ADVANCED_METHODS = "advanced_methods"
    EXISTING_TOOLS = "existing_tools"


INTEGRATION_LENSES: tuple[Lens, ...] = (
    Lens.MEANING,
    Lens.THEORY,
    Lens.PRACTICE,
    Lens.BEST_PRACTICES,
    Lens.EXPERT_VIEWS,
    Lens.ADVANCED_METHODS,
    Lens.EXISTING_TOOLS,
)

ALL_LENSES: tuple[Lens, ...] = INTEGRATION_LENSES + (Lens.ANALOGY,)


class SourceType(StrEnum):
    ACADEMIC = "academic"
    OFFICIAL_DOCS = "official_docs"
    EXPERT = "expert"
    NEWS = "news"
    FORUM = "forum"
    VENDOR = "vendor"
    OTHER = "other"


class ComplexityVerdict(StrEnum):
    COMPLEX = "complex"
    SIMPLE = "simple"


class NodeStatus(StrEnum):
    PENDING = "pending"
    LEAF = "leaf"
    SYNTHESIZED = "synthesized"
    PRUNED = "pruned"
    BUDGET_STOPPED = "budget_stopped"
    FAILED = "failed"


class StopReason(StrEnum):
    MAX_DEPTH = "max_depth"
    MAX_NODES = "max_nodes"
    MAX_FANOUT = "max_fanout"
    BUDGET = "budget"
    CANCELLED = "cancelled"
    STAGNATION = "stagnation"
    MEMOIZED = "memoized"
    DUPLICATE = "duplicate"


class SubKind(StrEnum):
    PREREQUISITE = "prerequisite"
    PART = "part"
    METHOD = "method"
    TOOL = "tool"
    TRADEOFF = "tradeoff"


# --------------------------------------------------------------------------- #
# Saida final (o JSON entregue)
# --------------------------------------------------------------------------- #


class CreditedClaim(Strict):
    text: str
    source_ids: list[SourceId] = Field(default_factory=list)


class ExpertView(Strict):
    who: str
    claim: str
    source_ids: list[SourceId] = Field(default_factory=list)


class AdvancedMethod(Strict):
    name: str
    when_to_use: str
    fit_score: float = Field(ge=0.0, le=1.0)
    source_ids: list[SourceId] = Field(default_factory=list)


class ExistingTool(Strict):
    name: str
    free: bool = False
    url: str = ""
    note: str = ""
    source_ids: list[SourceId] = Field(default_factory=list)


class Analysis(Strict):
    meaning: str = ""
    analogy: str = ""
    theory: str = ""
    practice: str = ""
    best_practices: list[CreditedClaim] = Field(default_factory=list)
    expert_views: list[ExpertView] = Field(default_factory=list)
    advanced_methods: list[AdvancedMethod] = Field(default_factory=list)
    existing_tools: list[ExistingTool] = Field(default_factory=list)
    fit_to_goal: str = ""
    consensus: str = ""
    conflicts: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class Complexity(Strict):
    score: float = Field(ge=0.0, le=1.0)
    verdict: ComplexityVerdict = ComplexityVerdict.SIMPLE
    reasons: list[str] = Field(default_factory=list)


class Node(Strict):
    id: NodeId = ""
    concept: str
    parent_id: NodeId | None = None
    children: list[NodeId] = Field(default_factory=list)
    depth: int = Field(ge=0)
    status: NodeStatus = NodeStatus.PENDING
    complexity: Complexity | None = None
    analysis: Analysis = Field(default_factory=Analysis)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    queries: list[str] = Field(default_factory=list)
    memoized_from: NodeId | None = None
    stop_reason: StopReason | None = None
    notes: list[str] = Field(default_factory=list)


class Source(Strict):
    url: str
    title: str = ""
    type: SourceType = SourceType.OTHER
    credibility: float = Field(default=0.5, ge=0.0, le=1.0)
    retrieved_at: dt.datetime = Field(default_factory=utcnow)
    snippet: str = ""


class Recommendation(Strict):
    text: str
    node_ids: list[NodeId] = Field(default_factory=list)
    source_ids: list[SourceId] = Field(default_factory=list)
    rationale: str = ""


class Intent(Strict):
    goal: str = ""
    type: IntentType = IntentType.MIXED
    constraints: list[str] = Field(default_factory=list)


class Budget(Strict):
    max_queries: int = 0
    max_pages: int = 0
    max_llm_calls: int = 0
    max_tokens: int = 0
    max_seconds: float = 0.0
    max_usd: float = 0.0
    queries: int = 0
    pages: int = 0
    llm_calls: int = 0
    tokens: int = 0
    seconds: float = 0.0
    usd: float = 0.0
    stopped_by: str | None = None


class Run(Strict):
    run_id: str
    query: str
    mode: RunMode = RunMode.STANDARD
    created_at: dt.datetime = Field(default_factory=utcnow)
    intent: Intent = Field(default_factory=Intent)
    summary: str = ""
    learning_path: list[NodeId] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    root_id: NodeId
    nodes: dict[NodeId, Node] = Field(default_factory=dict)
    sources: dict[SourceId, Source] = Field(default_factory=dict)
    budget: Budget = Field(default_factory=Budget)
    warnings: list[str] = Field(default_factory=list)

    def node(self, node_id: str) -> Node:
        try:
            return self.nodes[node_id]
        except KeyError as exc:
            raise KeyError(f"node inexistente: {node_id}") from exc

    def validate_tree(self) -> None:
        """Checagens de arvore/DAG: chaves batem com ids e nao ha ciclos."""
        for node_id, node in self.nodes.items():
            if node.id and node.id != node_id:
                raise ValueError(f"no {node_id} com id interno {node.id}")
            for child in node.children:
                if child not in self.nodes:
                    raise ValueError(f"no {node_id} aponta para filho inexistente {child}")
                if self.nodes[child].parent_id not in {None, node_id}:
                    raise ValueError(f"filho {child} com parent_id inconsistente")
            if node.parent_id is not None:
                parent = self.nodes.get(node.parent_id)
                if parent is None:
                    raise ValueError(f"no {node_id} com parent_id inexistente {node.parent_id}")
                if node_id not in parent.children:
                    raise ValueError(
                        f"no {node_id} nao esta na lista de filhos de {node.parent_id}"
                    )
        self._assert_acyclic(self.root_id, set())

    def _assert_acyclic(self, node_id: str, seen: set[str]) -> None:
        if node_id in seen:
            raise ValueError(f"ciclo na arvore no no {node_id}")
        seen.add(node_id)
        for child in self.nodes[node_id].children:
            self._assert_acyclic(child, seen)

    def prune_dangling_refs(self) -> None:
        """Remove referencias a nos inexistentes (ocorre quando budget para run em paralelo).

        Corrige duas inconsistencias:
        - node.children contendo ids nao presentes em self.nodes
        - node.parent_id apontando para no nao presente em self.nodes
        """
        for node in self.nodes.values():
            node.children = [c for c in node.children if c in self.nodes]
            if node.parent_id is not None and node.parent_id not in self.nodes:
                node.parent_id = None

    def ordered_nodes(self) -> list[Node]:
        """Nos na ordem da travessia (simples -> complexo)."""
        return [self.nodes[n] for n in self.learning_path if n in self.nodes]


class RunMeta(Strict):
    """Cabecalho leve para listar execucoes sem abrir o resultado inteiro."""

    run_id: str
    query: str
    mode: RunMode
    created_at: dt.datetime
    summary: str = ""
    nodes: int = 0
    sources: int = 0
    stopped_by: str | None = None


# --------------------------------------------------------------------------- #
# Contratos de saida estruturada do LLM (uma por etapa do pipeline)
# --------------------------------------------------------------------------- #


class LLMEnvelope(BaseModel):
    """Todo LLM recebe um schema e devolve um objeto com esta forma."""

    data: Any
    notes: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class ComplexityAssessment(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    verdict: ComplexityVerdict
    reasons: list[str] = Field(default_factory=list)
    sub_count_hint: int = Field(default=2, ge=0, le=8)


class SubConcept(BaseModel):
    concept: str
    kind: SubKind = SubKind.PART
    rationale: str = ""
    simpler_than_parent: bool = True


class Decomposition(BaseModel):
    subs: list[SubConcept] = Field(default_factory=list)


class CreditedClaimDraft(BaseModel):
    text: str
    source_ids: list[str] = Field(default_factory=list)


class ExpertViewDraft(BaseModel):
    who: str
    claim: str
    source_ids: list[str] = Field(default_factory=list)


class AdvancedMethodDraft(BaseModel):
    name: str
    when_to_use: str
    fit_score: float = Field(default=0.5, ge=0.0, le=1.0)
    source_ids: list[str] = Field(default_factory=list)


class ExistingToolDraft(BaseModel):
    name: str
    free: bool = False
    url: str = ""
    note: str = ""
    source_ids: list[str] = Field(default_factory=list)


class LensFinding(BaseModel):
    """Resultado de UMA lente sobre UM conceito, com citacao obrigatoria."""

    summary: str = ""
    claims: list[CreditedClaimDraft] = Field(default_factory=list)
    analogies: list[str] = Field(default_factory=list)
    expert_views: list[ExpertViewDraft] = Field(default_factory=list)
    advanced_methods: list[AdvancedMethodDraft] = Field(default_factory=list)
    tools: list[ExistingToolDraft] = Field(default_factory=list)
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    uncited_claims: list[str] = Field(default_factory=list)


class Integration(BaseModel):
    """Sintese de um no interno: como as partes se encaixam."""

    meaning: str = ""
    theory: str = ""
    practice: str = ""
    fit_to_goal: str = ""
    consensus: str = ""
    conflicts: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)


class RecommendationDraft(BaseModel):
    text: str
    node_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    rationale: str = ""


class RootSynthesis(BaseModel):
    summary: str = ""
    recommendations: list[RecommendationDraft] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class IntentDraft(BaseModel):
    goal: str
    type: IntentType = IntentType.MIXED
    constraints: list[str] = Field(default_factory=list)


class ImprovementProposal(BaseModel):
    title: str
    problem: str
    proposal: str
    impact: Literal["low", "medium", "high"] = "medium"
    effort: Literal["low", "medium", "high"] = "medium"
    rationale: str = ""


class Improvements(BaseModel):
    proposals: list[ImprovementProposal] = Field(default_factory=list)
