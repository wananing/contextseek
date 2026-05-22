"""Prometheus-compatible metrics export for ContextSeek."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from threading import Lock
from typing import Any

from contextseek.observability.audit import AuditLog
from contextseek.observability.audit import MetricPoint


@dataclass
class MetricsCollector:
    """Collects and aggregates MetricPoint entries for Prometheus-style export.

    Usage::

        collector = MetricsCollector()
        collector.record(MetricPoint(name="search_latency_ms", value=12.5))
        collector.record(MetricPoint(name="search_latency_ms", value=8.3))
        print(collector.export_prometheus())
    """

    _counters: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _histograms: dict[str, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )
    _lock: Lock = field(default_factory=Lock)

    def record(self, point: MetricPoint) -> None:
        """Record one metric point."""
        with self._lock:
            self._counters[point.name] += 1
            self._histograms[point.name].append(point.value)

    def record_many(self, points: list[MetricPoint]) -> None:
        """Record multiple metric points."""
        for point in points:
            self.record(point)

    def ingest_from_audit_log(self, audit_log: AuditLog) -> int:
        """Ingest all metric points from audit records."""
        count = 0
        for record in audit_log.records:
            for point in record.metrics:
                self.record(point)
                count += 1
        return count

    def get_counter(self, name: str) -> float:
        """Return total count of observations for a metric."""
        with self._lock:
            return self._counters.get(name, 0.0)

    def get_sum(self, name: str) -> float:
        """Return sum of all values for a metric."""
        with self._lock:
            values = self._histograms.get(name, [])
            return sum(values)

    def get_avg(self, name: str) -> float:
        """Return average value for a metric."""
        with self._lock:
            values = self._histograms.get(name, [])
            if not values:
                return 0.0
            return sum(values) / len(values)

    def export_prometheus(self, *, prefix: str = "contextseek") -> str:
        """Export all metrics in Prometheus text exposition format.

        Returns a string suitable for an HTTP endpoint consumed by Prometheus.
        """
        lines: list[str] = []
        with self._lock:
            for name in sorted(self._counters.keys()):
                metric_name = f"{prefix}_{name}_total"
                lines.append(f"# TYPE {metric_name} counter")
                lines.append(f"{metric_name} {self._counters[name]}")
                # Also emit sum and avg as gauges
                values = self._histograms.get(name, [])
                if values:
                    sum_name = f"{prefix}_{name}_sum"
                    avg_name = f"{prefix}_{name}_avg"
                    lines.append(f"# TYPE {sum_name} gauge")
                    lines.append(f"{sum_name} {sum(values):.6f}")
                    lines.append(f"# TYPE {avg_name} gauge")
                    lines.append(f"{avg_name} {sum(values) / len(values):.6f}")
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        """Clear all collected metrics."""
        with self._lock:
            self._counters.clear()
            self._histograms.clear()

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of current metrics."""
        with self._lock:
            result: dict[str, Any] = {}
            for name in sorted(self._counters.keys()):
                values = self._histograms.get(name, [])
                result[name] = {
                    "count": self._counters[name],
                    "sum": sum(values),
                    "avg": sum(values) / len(values) if values else 0.0,
                    "min": min(values) if values else 0.0,
                    "max": max(values) if values else 0.0,
                }
            return result


__all__ = ["MetricsCollector"]
