"""ContextSeek client helpers for AppWorld evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from contextseek import ContextSeek, ContextSeekSettings, SourceType, Stage
from contextseek.config.settings import (
    EmbeddingSettings,
    EvolutionSettings,
    LLMSettings,
    ObservabilitySettings,
    RetrievalSettings,
    SecuritySettings,
    StorageSettings,
    SummarizerSettings,
)


@dataclass
class RetrievalPayload:
    """Prompt-ready ContextSeek retrieval output."""

    text: str = ""
    count: int = 0
    item_ids: list[str] = field(default_factory=list)


def _build_settings(config: dict[str, Any]) -> ContextSeekSettings:
    """Build ContextSeek settings from the ``contextseek`` YAML section."""
    storage = StorageSettings(**config.get("storage", {}))
    embedding = EmbeddingSettings(**config.get("embedding", {}))
    llm = LLMSettings(**config.get("llm", {}))
    summarizer = SummarizerSettings(**config.get("summarizer", {}))
    retrieval = RetrievalSettings(**config.get("retrieval", {}))
    evolution = EvolutionSettings(**config.get("evolution", {}))
    security = SecuritySettings(**config.get("security", {}))
    observability = ObservabilitySettings(**config.get("observability", {}))
    return ContextSeekSettings(
        storage=storage,
        embedding=embedding,
        llm=llm,
        summarizer=summarizer,
        retrieval=retrieval,
        evolution=evolution,
        security=security,
        observability=observability,
    )


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _hit_text(hit: Any) -> str:
    item = hit.item
    if item.summary:
        return item.summary
    if item.content is not None:
        return _content_to_text(item.content)
    return item.abstract or ""


def _response_to_payload(response: Any, *, max_tokens: int) -> RetrievalPayload:
    char_budget = max(0, max_tokens * 4)
    lines: list[str] = []
    item_ids: list[str] = []
    used = 0
    for idx, hit in enumerate(response, 1):
        text = _hit_text(hit).strip()
        if not text:
            continue
        header = f"[Retrieved context {idx}] id={hit.item.id} score={hit.score:.4f}"
        block = f"{header}\n{text}"
        if char_budget and used + len(block) > char_budget:
            remaining = char_budget - used - len(header) - 1
            if remaining <= 0:
                break
            block = f"{header}\n{text[:remaining].rstrip()}"
        lines.append(block)
        item_ids.append(hit.item.id)
        used += len(block) + 2
        if char_budget and used >= char_budget:
            break
    return RetrievalPayload(text="\n\n".join(lines), count=len(item_ids), item_ids=item_ids)


class ContextSeekClient:
    """Small domain client used by the AppWorld ReAct agent and pipeline."""

    def __init__(
        self,
        *,
        config: dict[str, Any] | None = None,
        scope: str,
    ) -> None:
        self.scope = scope
        self.config = config or {}
        self.ctx = _build_contextseek(self.config)

    @classmethod
    def from_config(cls, config: dict[str, Any], *, scope: str) -> "ContextSeekClient":
        return cls(config=config, scope=scope)

    def retrieve_for_task(self, instruction: str, *, max_tokens: int = 1200) -> RetrievalPayload:
        """Retrieve initial background for a new AppWorld task."""
        response = self.ctx.retrieve(
            instruction,
            scope=self.scope,
            k=8,
        )
        return _response_to_payload(response, max_tokens=max_tokens)

    def retrieve_for_error(self, observation: str, *, limit: int = 3) -> RetrievalPayload:
        """Retrieve prior context for an execution error observation."""
        hits = self.ctx.retrieve(
            observation[:500],
            scope=self.scope,
            k=limit,
            filters={"tags": ["failure"]},
        )
        if not hits:
            hits = self.ctx.retrieve(
                observation[:500],
                scope=self.scope,
                k=limit,
            )
        lines: list[str] = []
        item_ids: list[str] = []
        for idx, hit in enumerate(hits, 1):
            item_ids.append(hit.item.id)
            lines.append(
                f"[Prior error context {idx}] id={hit.item.id} score={hit.score:.4f}\n"
                f"{_hit_text(hit)}"
            )
        return RetrievalPayload(text="\n\n".join(lines), count=len(hits), item_ids=item_ids)

    def store_trajectory(
        self,
        *,
        task_id: str,
        instruction: str,
        steps: list[dict[str, Any]],
        success: bool,
    ) -> str:
        """Store a raw task trace for later distillation and debugging."""
        item = self.ctx.add(
            {
                "kind": "appworld_trajectory",
                "task_id": task_id,
                "instruction": instruction,
                "success": success,
                "steps": steps,
            },
            scope=self.scope,
            source=f"appworld:{task_id}",
            source_type=SourceType.external_api,
            tags=["appworld", "trajectory", "success" if success else "failure"],
            stage=Stage.raw,
            confidence=0.8 if success else 0.5,
        )
        return item.id

    def store_experience(
        self,
        *,
        title: str,
        content: str | dict[str, Any],
        source: str,
        tags: list[str] | None = None,
        stage: Stage = Stage.knowledge,
        confidence: float = 0.75,
    ) -> str:
        """Store distilled reusable AppWorld knowledge."""
        normalized_tags = ["appworld", "experience", *(tags or [])]
        item = self.ctx.add(
            {
                "title": title,
                "body": _content_to_text(content),
            },
            scope=self.scope,
            source=source,
            source_type=SourceType.distillation,
            tags=list(dict.fromkeys(normalized_tags)),
            stage=stage,
            confidence=confidence,
        )
        return item.id

    def apply_success_feedback(self, item_ids: list[str]) -> int:
        """Boost retrieved items that were used during a successful task."""
        updated = 0
        for item_id in dict.fromkeys(item_ids):
            try:
                ref = self.ctx.resolver.ref_for(self.scope, item_id)
                self.ctx.feedback(
                    ref,
                    scope=self.scope,
                    score=0.2,
                    reason="retrieved_context_on_successful_appworld_task",
                )
                updated += 1
            except Exception:
                continue
        return updated

    def compact(self) -> dict[str, Any]:
        """Run ContextSeek compaction/evolution for the configured scope."""
        report = self.ctx.compact(scope=self.scope)
        return {
            "merged_count": report.merged_count,
            "archived_count": report.archived_count,
            "evolved_count": report.evolved_count,
            "details": report.details,
        }

    def overview(self) -> dict[str, Any]:
        """Return a serializable stage overview for reporting/debugging."""
        report = self.ctx.overview(scope=self.scope)
        return {
            "total_items": report.total_items,
            "stage_distribution": report.stage_distribution,
            "pending_extraction": report.pending_extraction,
            "pending_convergence": report.pending_convergence,
            "distill_candidates": report.distill_candidates,
        }


def _build_contextseek(config: dict[str, Any]) -> ContextSeek:
    """Build ContextSeek for the AppWorld harness, including OceanBase storage."""
    settings = _build_settings(config)
    storage_cfg = config.get("storage", {})
    backend = str(storage_cfg.get("backend", settings.storage.backend)).lower()
    if backend not in {"oceanbase", "ob"}:
        return ContextSeek.from_settings(settings)
    return _build_oceanbase_contextseek(config, settings)


def _build_oceanbase_contextseek(
    config: dict[str, Any],
    settings: ContextSeekSettings,
) -> ContextSeek:
    """Build an OceanBase-backed ContextSeek instance for storage A/B tests."""
    import seekvfs

    from contextseek.storage import OceanBaseBackend, SeekVFSStorageAdapter
    from contextseek.config.factory import build_embedder, build_llm, build_summarizer
    from contextseek.config.settings import to_strategy_config
    from contextseek.routing.resolver import ScopeResolver

    embedder = build_embedder(settings.embedding)
    if embedder is None:
        raise ValueError(
            "contextseek.storage.backend=oceanbase requires contextseek.embedding "
            "to configure a real embedding provider."
        )

    shared_llm = build_llm(settings.llm)
    summarizer = build_summarizer(settings.summarizer, llm=shared_llm)

    storage_cfg = config.get("storage", {})
    ob_cfg = storage_cfg.get("oceanbase", {})
    vector_dims = int(ob_cfg.get("vector_dims") or settings.embedding.dims or 0)
    if vector_dims <= 0:
        raise ValueError("OceanBase storage requires vector_dims or embedding.dims")

    backend = OceanBaseBackend(
        table_name=ob_cfg.get("table_name", "contextseek_appworld"),
        vector_dims=vector_dims,
        host=ob_cfg.get("host", "127.0.0.1"),
        port=str(ob_cfg.get("port", "2881")),
        user=ob_cfg.get("user", "root@test"),
        password=ob_cfg.get("password", ""),
        db_name=ob_cfg.get("db_name", "contextseek"),
        fulltext_parser=ob_cfg.get("fulltext_parser", "ngram"),
        vidx_metric_type=ob_cfg.get("metric", ob_cfg.get("vidx_metric_type", "cosine")),
        vector_weight=float(ob_cfg.get("vector_weight", 0.7)),
        fts_weight=float(ob_cfg.get("fts_weight", 0.3)),
        rrf_k=int(ob_cfg.get("rrf_k", 60)),
    )
    backend.initialize()

    scheme = settings.storage.uri_scheme
    vfs = seekvfs.VFS({scheme: {"backend": backend}}, scheme=scheme)
    adapter = SeekVFSStorageAdapter(vfs)
    strategy = to_strategy_config(settings)

    audit_log = None
    if settings.observability.audit_enabled:
        from contextseek.observability.audit import AuditLog

        audit_log = AuditLog(
            persist_path=settings.observability.audit_path,
            metrics_path=(
                settings.observability.metrics_path
                if settings.observability.metrics_enabled
                else None
            ),
        )

    evolution_engine = None
    if settings.evolution.enabled:
        from contextseek.evolution.engine import EvolutionEngine

        evolution_engine = EvolutionEngine()

    return ContextSeek(
        adapter=adapter,
        resolver=ScopeResolver(uri_scheme=scheme),
        embedder=embedder,
        summarizer=summarizer,
        evolution_engine=evolution_engine,
        audit_log=audit_log,
        strategy=strategy,
        _strategy_version=strategy.version,
    )
