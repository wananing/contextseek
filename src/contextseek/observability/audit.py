"""Request-level audit records."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MetricPoint:
    """One metrics sample emitted by a request."""

    name: str
    value: float
    unit: str = "count"
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class AuditRecord:
    """Audit metadata for retrieval and write operations."""

    request_id: str
    action: str
    scope: str
    policy_version: str
    actor: dict[str, Any] = field(default_factory=dict)
    request: dict[str, Any] = field(default_factory=dict)
    source: str | None = None
    reason: str | None = None
    status: str = "ok"
    elapsed_ms: float = 0.0
    detail: dict[str, Any] = field(default_factory=dict)
    metrics: list[MetricPoint] = field(default_factory=list)
    provenance_chain: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AuditLog:
    """Audit log with optional JSONL persistence for local runtimes."""

    records: list[AuditRecord] = field(default_factory=list)
    persist_path: str | None = None
    metrics_path: str | None = None

    def __post_init__(self) -> None:
        if self.persist_path is None:
            return
        path = Path(self.persist_path)
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            self.records.append(_record_from_dict(json.loads(line)))

    def append(self, record: AuditRecord) -> None:
        self.records.append(record)
        if self.persist_path is not None:
            path = Path(self.persist_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(_record_to_dict(record), ensure_ascii=False) + "\n")
        if self.metrics_path is not None:
            path = Path(self.metrics_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.export_prometheus(), encoding="utf-8")

    def latest(self, *, action: str | None = None) -> AuditRecord | None:
        """Return latest record, optionally filtered by action."""
        if action is None:
            return self.records[-1] if self.records else None
        for record in reversed(self.records):
            if record.action == action:
                return record
        return None

    def metric_series(self, name: str) -> list[float]:
        """Return all metric values for one metric name."""
        values: list[float] = []
        for record in self.records:
            for metric in record.metrics:
                if metric.name == name:
                    values.append(metric.value)
        return values

    def recent(self, *, limit: int = 50, action: str | None = None) -> list[AuditRecord]:
        """Return recent audit records in reverse chronological order."""
        safe_limit = max(1, min(limit, 200))
        if action is None:
            selected = self.records[-safe_limit:]
        else:
            filtered = [record for record in self.records if record.action == action]
            selected = filtered[-safe_limit:]
        return list(reversed(selected))

    def request_trace(self, request_id: str) -> list[AuditRecord]:
        """Return all records for one request id."""
        return [record for record in self.records if record.request_id == request_id]

    def retrieval_replay(self, request_id: str) -> dict[str, Any] | None:
        """Return enough retrieve-audit data to replay or debug one retrieval."""
        for record in reversed(self.records):
            if record.request_id == request_id and record.action == "retrieve":
                return {
                    "request_id": record.request_id,
                    "scope": record.scope,
                    "policy_version": record.policy_version,
                    "detail": record.detail,
                    "provenance_chain": record.provenance_chain,
                    "metrics": [asdict(item) for item in record.metrics],
                    "actor": record.actor,
                    "request": record.request,
                    "source": record.source,
                    "reason": record.reason,
                    "created_at": record.created_at.isoformat(),
                }
        return None

    def export_prometheus(self) -> str:
        """Export request metrics in Prometheus text exposition format."""
        lines = [
            "# HELP contextseek_request_metric ContextSeek request-level metric.",
            "# TYPE contextseek_request_metric gauge",
        ]
        for record in self.records:
            base_labels = {
                "action": record.action,
                "scope": record.scope,
                "status": record.status,
                "policy_version": record.policy_version,
            }
            labels = _labels({**base_labels, "name": "elapsed_ms"})
            lines.append(f"contextseek_request_metric{{{labels}}} {record.elapsed_ms}")
            for metric in record.metrics:
                labels = _labels({**base_labels, **metric.tags, "name": metric.name})
                lines.append(f"contextseek_request_metric{{{labels}}} {metric.value}")
        return "\n".join(lines) + "\n"


def _labels(values: dict[str, str]) -> str:
    return ",".join(f'{key}="{str(value).replace(chr(34), "")}"' for key, value in values.items())


def _record_to_dict(record: AuditRecord) -> dict[str, Any]:
    payload = asdict(record)
    payload["created_at"] = record.created_at.isoformat()
    return payload


def _record_from_dict(payload: dict[str, Any]) -> AuditRecord:
    return AuditRecord(
        request_id=str(payload["request_id"]),
        action=str(payload["action"]),
        scope=str(payload.get("scope", "")),
        policy_version=str(payload.get("policy_version", "")),
        actor=dict(payload.get("actor", {})),
        request=dict(payload.get("request", {})),
        source=payload.get("source"),
        reason=payload.get("reason"),
        status=str(payload.get("status", "ok")),
        elapsed_ms=float(payload.get("elapsed_ms", 0.0)),
        detail=dict(payload.get("detail", {})),
        metrics=[
            MetricPoint(
                name=str(item["name"]),
                value=float(item["value"]),
                unit=str(item.get("unit", "count")),
                tags=dict(item.get("tags", {})),
            )
            for item in payload.get("metrics", [])
        ],
        provenance_chain=list(payload.get("provenance_chain", [])),
        created_at=datetime.fromisoformat(str(payload["created_at"])),
    )
