from __future__ import annotations

import asyncio
import datetime as dt
import logging
import uuid
from collections.abc import Callable
from typing import Any

from ..audit import AuditLog
from ..config import IdFactory, ModePreset, Settings
from ..llm.base import LLMProvider
from ..models import (
    Analysis,
    Complexity,
    ComplexityVerdict,
    Intent,
    IntentDraft,
    Lens,
    Node,
    NodeStatus,
    Run,
    RunMode,
    StopReason,
)
from ..prompts import render
from ..search.cache import Cache
from ..search.fetch import Fetcher
from ..search.searxng import SearxngClient
from . import complexity as complexity_mod
from . import decompose as decompose_mod
from .budget import BudgetExceeded, BudgetTracker
from .llm_runner import LLMRunner
from .research import ResearchEngine, ResearchResult, SourceRegistry
from .synthesize import (
    analysis_from_findings,
    cited_sources,
    integrate,
    node_summary,
    remap_analysis,
    synthesize_root,
)

log = logging.getLogger(__name__)

EventCallback = Callable[[dict[str, Any]], None]

INTEGRATION_LENSES: tuple[Lens, ...] = (
    Lens.MEANING,
    Lens.THEORY,
    Lens.PRACTICE,
    Lens.BEST_PRACTICES,
    Lens.EXPERT_VIEWS,
    Lens.ADVANCED_METHODS,
    Lens.EXISTING_TOOLS,
)


class Cancelled(RuntimeError):
    pass


class Orchestrator:
    """A cadeia de abstracao: decompõe, pesquisa por lentes e reconstroi de baixo para cima."""

    def __init__(
        self,
        settings: Settings,
        provider: LLMProvider,
        *,
        cache: Cache | None = None,
        audit: AuditLog | None = None,
        on_event: EventCallback | None = None,
        search: SearxngClient | None = None,
        fetcher: Fetcher | None = None,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.cache = cache
        self.audit = audit
        self.on_event = on_event
        self.budget = BudgetTracker.from_settings(settings, RunMode.STANDARD.value)
        self.registry = SourceRegistry(IdFactory(settings.node_prefix, settings.source_prefix))
        self.semaphore = asyncio.Semaphore(max(1, settings.budget_concurrency))
        self.cancel_event = asyncio.Event()
        self.nodes: dict[str, Node] = {}
        self.memo: dict[str, str] = {}
        self._counter = 0
        self._search: SearxngClient | None = search
        self._fetcher: Fetcher | None = fetcher
        self._llm: LLMRunner | None = None

    # --- infra ------------------------------------------------------------- #

    def _llm_runner(self) -> LLMRunner:
        if self._llm is None:
            self._llm = LLMRunner(
                self.settings, self.provider, self.budget, self.cache, self.audit, self.on_event
            )
        return self._llm

    def _research_engine(self) -> ResearchEngine:
        if self._search is None:
            self._search = SearxngClient(
                self.settings, self.budget, cache=self.cache, audit=self.audit
            )
        if self._fetcher is None:
            self._fetcher = Fetcher(self.settings, self.budget, cache=self.cache, audit=self.audit)
        return ResearchEngine(
            self.settings, self._search, self._fetcher, self._llm_runner(), self.registry
        )

    async def aclose(self) -> None:
        if self._search is not None:
            await self._search.aclose()
        if self._fetcher is not None:
            await self._fetcher.aclose()
        await self.provider.aclose()

    def cancel(self) -> None:
        self.cancel_event.set()
        self.budget.stop(StopReason.CANCELLED)

    def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            self.budget.stop(StopReason.CANCELLED)
            raise Cancelled()

    def _new_id(self) -> str:
        self._counter += 1
        return f"{self.settings.node_prefix}{self._counter}"

    def _event(self, payload: dict[str, Any]) -> None:
        if self.on_event is not None:
            try:
                self.on_event(payload)
            except Exception:  # pragma: no cover
                log.exception("falha no callback de progresso")

    def _audit(self, event: str, **fields: Any) -> None:
        if self.audit is not None:
            self.audit.record(event, **fields)

    # --- run ---------------------------------------------------------------- #

    async def run(
        self,
        query: str,
        *,
        mode: str = RunMode.STANDARD.value,
        lenses: tuple[Lens, ...] | None = None,
        max_depth: int | None = None,
        max_fanout: int | None = None,
        max_nodes: int | None = None,
        goal_context: str = "",
    ) -> Run:
        profile = self.settings.mode(mode)
        self.budget = BudgetTracker.from_settings(self.settings, mode)
        self.registry = SourceRegistry(
            IdFactory(self.settings.node_prefix, self.settings.source_prefix)
        )
        self.nodes = {}
        self.memo = {}
        self._counter = 0

        depth_limit = min(max_depth or profile.max_depth, self.settings.max_depth_hard_cap)
        fanout_limit = max_fanout or profile.max_fanout
        node_limit = max_nodes or 24
        chosen_lenses = tuple(lenses) if lenses else profile.lenses

        run_id = f"r_{dt.datetime.now(dt.UTC):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"
        if self.audit is not None:
            self.audit.bind(run_id)
        intent = await self._intent(query, goal_context)

        run = Run(run_id=run_id, query=query, mode=RunMode(mode), intent=intent, root_id="n1")
        self._event({"event": "start", "run_id": run_id, "query": query, "mode": mode})

        root = await self._guarded(
            self._abstract,
            query,
            goal=intent.goal,
            depth=0,
            parent_id=None,
            profile=profile,
            lenses=chosen_lenses,
            depth_limit=depth_limit,
            fanout_limit=fanout_limit,
            node_limit=node_limit,
        )

        run.nodes = self._fix_memo_links(self.nodes)
        run.root_id = root.id
        run.learning_path = _post_order(self.nodes, root.id)
        run.sources = dict(self.registry.sources)

        rec_lines = [
            f"- {node_id}: {node_summary(self.nodes[node_id])}"
            for node_id in run.learning_path
            if node_id in self.nodes
        ]
        summary = ""
        recommendations = []
        conflicts: list[str] = []
        open_questions: list[str] = []
        try:
            summary, recommendations, conflicts, open_questions = await synthesize_root(
                self._llm_runner(), run, intent.goal, rec_lines
            )
        except (BudgetExceeded, Cancelled):
            self.budget.stop(
                StopReason.CANCELLED if self.cancel_event.is_set() else StopReason.BUDGET
            )
        except Exception as exc:
            log.warning("sintese final falhou: %s", exc)
            run.warnings.append(f"sintese final falhou: {exc}")

        for text in conflicts:
            if text and text not in root.analysis.conflicts:
                root.analysis.conflicts.append(text)
        for text in open_questions:
            if text and text not in root.analysis.open_questions:
                root.analysis.open_questions.append(text)
        root.analysis.fit_to_goal = root.analysis.fit_to_goal or intent.goal

        run.summary = summary or root.analysis.meaning or root.analysis.practice or query
        run.recommendations = recommendations
        run.budget = self.budget.snapshot()
        if self.cancel_event.is_set():
            run.warnings.append("execucao cancelada: arvore parcial")
        # Garante consistência da árvore mesmo quando budget interrompe nós em paralelo
        run.prune_dangling_refs()
        self._event({"event": "done", "run_id": run_id, "nodes": len(self.nodes)})
        self._audit(
            "run_finished",
            nodes=len(self.nodes),
            sources=len(run.sources),
            stopped_by=run.budget.stopped_by,
        )
        return run

    async def _reuse_cached(self, concept: str, goal: str, node: Node) -> bool:
        """Cache entre execucoes: conceito ja pesquisado vira referencia, nao pesquisa."""
        payload = await self._cached_concept(concept, goal)
        if not payload or not payload.get("analysis"):
            return False
        mapping: dict[str, str] = {}
        for source in payload.get("sources") or []:
            mapping[source.get("id", "")] = self.registry.register(
                source.get("url", ""), source.get("title", ""), source.get("snippet", "")
            )
        node.analysis = remap_analysis(Analysis.model_validate(payload["analysis"]), mapping)
        node.confidence = float(payload.get("confidence", 0.5))
        node.status = NodeStatus.LEAF
        node.stop_reason = StopReason.DUPLICATE
        node.notes.append("reaproveitado do cache de conceitos (run anterior)")
        self._audit("concept_cache_hit", node_id=node.id, concept=concept)
        self._event({"event": "node_cache", "node_id": node.id, "concept": concept})
        return True

    async def _persist_concept(self, concept: str, goal: str, node: Node) -> None:
        if self.cache is None or not node.analysis.meaning:
            return
        sources = [
            self.registry.sources[sid].model_dump(mode="json") | {"id": sid}
            for sid in sorted(cited_sources(node.analysis))
            if sid in self.registry.sources
        ]
        await self.cache.put_concept(
            concept,
            goal,
            {
                "analysis": node.analysis.model_dump(mode="json"),
                "sources": sources,
                "confidence": node.confidence,
            },
        )

    async def _cached_concept(self, concept: str, goal: str) -> dict[str, Any] | None:
        if self.cache is None:
            return None
        return await self.cache.get_concept(concept, goal, self.settings.concept_cache_ttl_hours)

    def _fix_memo_links(self, nodes: dict[str, Node]) -> dict[str, Node]:
        """Nos memoizados podem ter copiado a analise antes de o no de origem terminar."""
        for node in nodes.values():
            if node.stop_reason is not StopReason.MEMOIZED or node.memoized_from is None:
                continue
            if node.analysis.meaning or node.analysis.practice:
                continue
            source = nodes.get(node.memoized_from)
            if source is None or source.id == node.id:
                continue
            node.analysis = source.analysis.model_copy(deep=True)
            node.complexity = source.complexity
            node.confidence = source.confidence
            node.queries = list(source.queries)
        return nodes

    async def _intent(self, query: str, goal_context: str) -> Intent:
        text = query if not goal_context else f"{query}\n\nContexto: {goal_context}"
        try:
            draft: IntentDraft = await self._llm_runner().run(
                IntentDraft, stage="intent", prompt=render("intent", query=text)
            )
            return Intent(
                goal=draft.goal or goal_context or query,
                type=draft.type,
                constraints=draft.constraints,
            )
        except Exception as exc:
            log.warning("intencao nao obtida (%s); usando a query como objetivo", exc)
            return Intent(goal=goal_context or query)

    async def _guarded(self, coro_factory: Callable[[], Any], *args: Any, **kwargs: Any) -> Node:
        """Executa uma criacao de no sem deixar erro derrubar o run inteiro."""
        try:
            return await coro_factory(*args, **kwargs)
        except (Cancelled, BudgetExceeded) as exc:
            reason = (
                StopReason.CANCELLED
                if self.cancel_event.is_set() or isinstance(exc, Cancelled)
                else StopReason.BUDGET
            )
            self.budget.stop(reason)
            concept = kwargs.get("concept") or (args[0] if args else "desconhecido")
            depth = kwargs.get("depth", 0)
            parent_id = kwargs.get("parent_id")
            return self._stopped_node(str(concept), depth, parent_id, reason)
        except Exception as exc:
            log.exception("falha ao criar no")
            concept = kwargs.get("concept") or (args[0] if args else "desconhecido")
            depth = kwargs.get("depth", 0)
            parent_id = kwargs.get("parent_id")
            node = self._new_node(concept, depth, parent_id, NodeStatus.FAILED)
            node.notes.append(f"falha: {exc}")
            self._audit("node_failed", node_id=node.id, error=str(exc))
            return node

    def _new_node(
        self, concept: str, depth: int, parent_id: str | None, status: NodeStatus
    ) -> Node:
        node = Node(
            id=self._new_id(), concept=concept, depth=depth, parent_id=parent_id, status=status
        )
        self.nodes[node.id] = node
        return node

    def _stopped_node(
        self, concept: str, depth: int, parent_id: str | None, reason: StopReason
    ) -> Node:
        node = self._new_node(concept, depth, parent_id, NodeStatus.BUDGET_STOPPED)
        node.stop_reason = reason
        node.notes.append(f"parado por {reason.value}")
        self._event(
            {
                "event": "node_stopped",
                "node_id": node.id,
                "concept": concept,
                "reason": reason.value,
            }
        )
        return node

    # --- recursao ----------------------------------------------------------- #

    async def _abstract(
        self,
        concept: str,
        *,
        goal: str,
        depth: int,
        parent_id: str | None,
        profile: ModePreset,
        lenses: tuple[Lens, ...],
        depth_limit: int,
        fanout_limit: int,
        node_limit: int,
    ) -> Node:
        self._check_cancel()
        node_id = self._new_id()
        key = decompose_mod.normalize(concept)
        self._audit("node_start", node_id=node_id, concept=concept, depth=depth)
        self._event({"event": "node_start", "node_id": node_id, "concept": concept, "depth": depth})
        node = Node(id=node_id, concept=concept, depth=depth, parent_id=parent_id)
        # registra desde o inicio: limite de nos e memo precisam enxergar nos em voo
        self.nodes[node_id] = node

        if len(self.nodes) >= node_limit:
            self.budget.stop(StopReason.MAX_NODES)
            node.status = NodeStatus.PRUNED
            node.stop_reason = StopReason.MAX_NODES
            node.notes.append(f"limite de nos ({node_limit})")
            # nao entra na arvore: o pai so liga filhos que existem de fato
            self.nodes.pop(node_id, None)
            self._event(
                {"event": "node_stopped", "node_id": node_id, "reason": StopReason.MAX_NODES.value}
            )
            return node

        original_id = self.memo.get(key)
        if original_id is not None:
            node.status = NodeStatus.LEAF
            node.stop_reason = StopReason.MEMOIZED
            node.memoized_from = original_id
            node.notes.append(f"conceito ja pesquisado no no {original_id}: reaproveitado")
            source = self.nodes.get(original_id)
            if source is not None:
                node.analysis = source.analysis.model_copy(deep=True)
                node.complexity = source.complexity
                node.confidence = source.confidence
                node.queries = list(source.queries)
            self.nodes[node_id] = node
            self._event({"event": "node_memo", "node_id": node_id, "from": original_id})
            return node
        self.memo[key] = node_id

        reused = await self._reuse_cached(concept, goal, node)
        if reused:
            return node

        complexity = await self._complexity(concept, goal, depth)
        node.complexity = complexity
        wants_children = complexity.verdict is ComplexityVerdict.COMPLEX
        depth_exhausted = depth >= depth_limit

        subs = []
        if wants_children and not depth_exhausted:
            subs = await self._decompose(concept, goal, depth, fanout_limit)
            if wants_children and not subs:
                node.stop_reason = StopReason.STAGNATION
                node.notes.append("decomposicao devolveu sub-conceitos iguais ao pai: parado aqui")
                self._audit("stagnation", node_id=node_id, concept=concept)
        elif wants_children and depth_exhausted:
            node.notes.append(
                f"complexo, mas profundidade maxima ({depth_limit}) atingida: "
                "expandido sem decompor"
            )
            node.stop_reason = StopReason.MAX_DEPTH
            self._audit("max_depth", node_id=node_id, depth=depth, limit=depth_limit)

        children: list[Node] = []
        if subs:
            self._audit("decompose", node_id=node_id, subs=[s.concept for s in subs])
            results = await asyncio.gather(
                *[
                    self._child(
                        sub.concept,
                        goal=goal,
                        depth=depth + 1,
                        parent_id=node_id,
                        profile=profile,
                        lenses=lenses,
                        depth_limit=depth_limit,
                        fanout_limit=fanout_limit,
                        node_limit=node_limit,
                    )
                    for sub in subs
                ]
            )
            children = [r for r in results if r is not None and r.id in self.nodes]
            if not children:
                node.stop_reason = node.stop_reason or StopReason.STAGNATION
                node.notes.append("nenhum sub-conceito sobreviveu")
            node.children = [c.id for c in children]

        own_lenses = (
            tuple(lens for lens in lenses if lens in INTEGRATION_LENSES)
            if children
            else tuple(lenses)
        )
        findings, source_ids, queries, notes = await self._research(concept, goal, own_lenses, node)
        node.queries = queries
        node.notes.extend(notes)

        integration = await self._integrate(concept, goal, children, findings, node)
        analysis, confidence = analysis_from_findings(
            findings, integration, set(self.registry.sources)
        )
        node.analysis = analysis
        node.confidence = confidence
        node.status = NodeStatus.SYNTHESIZED if children else NodeStatus.LEAF
        if not source_ids and not children:
            node.status = NodeStatus.PRUNED
            node.notes.append("sem fontes: considerado folha sem pesquisa")
        await self._persist_concept(concept, goal, node)

        self.nodes[node_id] = node
        self._audit(
            "node_done",
            node_id=node_id,
            status=node.status.value,
            children=len(children),
            confidence=confidence,
        )
        self._event(
            {
                "event": "node_done",
                "node_id": node_id,
                "concept": concept,
                "depth": depth,
                "status": node.status.value,
                "confidence": confidence,
                "children": node.children,
            }
        )
        return node

    async def _child(self, concept: str, **kwargs: Any) -> Node | None:
        async with self.semaphore:
            return await self._guarded(self._abstract, concept, **kwargs)

    async def _complexity(self, concept: str, goal: str, depth: int) -> Complexity:
        try:
            return await complexity_mod.assess_complexity(self._llm_runner(), concept, goal, depth)
        except (BudgetExceeded, Cancelled):
            raise
        except Exception as exc:
            log.warning("complexidade falhou em %s: %s", concept, exc)
            return Complexity(
                score=0.3, verdict=ComplexityVerdict.SIMPLE, reasons=[f"fallback: {exc}"]
            )

    async def _decompose(self, concept: str, goal: str, depth: int, fanout: int) -> list[Any]:
        try:
            subs = await decompose_mod.decompose(self._llm_runner(), concept, goal, depth, fanout)
        except (BudgetExceeded, Cancelled):
            raise
        except Exception as exc:
            log.warning("decomposicao falhou em %s: %s", concept, exc)
            return []
        kept = [
            s
            for s in subs
            if decompose_mod.similarity(s.concept, concept) < decompose_mod.DUPLICATE_THRESHOLD
        ]
        if len(kept) < len(subs):
            self._audit("stagnation", concept=concept, discarded=len(subs) - len(kept))
        return kept

    async def _research(
        self, concept: str, goal: str, lenses: tuple[Lens, ...], node: Node
    ) -> tuple[dict[Lens, Any], set[str], list[str], list[str]]:
        if not lenses:
            return {}, set(), [], []
        try:
            result: ResearchResult = await self._research_engine().research(
                concept, goal, lenses, node_id=node.id
            )
        except (BudgetExceeded, Cancelled):
            raise
        except Exception as exc:
            node.notes.append(f"pesquisa falhou: {exc}")
            return {}, set(), [], []
        notes: list[str] = []
        if result.lens_errors:
            notes.append("lentes com falha: " + ", ".join(result.lens_errors))
        if not result.source_ids:
            notes.append("nenhuma fonte obtida")
        return result.findings, set(result.source_ids), result.queries, notes

    async def _integrate(
        self,
        concept: str,
        goal: str,
        children: list[Node],
        findings: dict[Lens, Any],
        node: Node,
    ) -> Any:
        try:
            return await integrate(self._llm_runner(), concept, goal, children, findings)
        except (BudgetExceeded, Cancelled):
            raise
        except Exception as exc:
            log.warning("integracao falhou em %s: %s", concept, exc)
            node.notes.append(f"integracao falhou: {exc}")
            return None


def _post_order(nodes: dict[str, Node], root_id: str) -> list[str]:
    """Travessia pos-ordem: as folhas (o basico) primeiro, a raiz por ultimo."""
    order: list[str] = []

    def visit(node_id: str) -> None:
        node = nodes.get(node_id)
        if node is None:
            return
        for child_id in node.children:
            visit(child_id)
        if node.status is NodeStatus.BUDGET_STOPPED:
            return
        if node.analysis.meaning or node.analysis.practice or node.analysis.theory:
            order.append(node_id)

    visit(root_id)
    return order


__all__ = ["Orchestrator", "Cancelled", "INTEGRATION_LENSES"]
