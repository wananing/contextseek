# Observability

ContextSeek emits two observability streams: an **audit log** (JSONL, one record per API call) and **Prometheus-compatible metrics** (exported to a text file). Both are off by default.

---

## Audit log

Enable the audit log in `.env`:

```env
OBSERVABILITY_AUDIT_ENABLED=true
OBSERVABILITY_AUDIT_PATH=.contextseek/audit.jsonl
```

Every `add()`, `retrieve()`, `compact()`, `dream()`, `feedback()`, `forget()`, `delete()`, and `evidence_chain()` call appends one JSON line to the file.

### Record structure

Each line is a JSON object with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | string | Auto-generated UUID per call |
| `action` | string | API method name: `add`, `retrieve`, `compact`, etc. |
| `scope` | string | Scope the operation ran against |
| `policy_version` | string | Strategy version label (from `pin()`) |
| `actor` | object | Who made the call (set via `ctx.tag()`) |
| `request` | object | Request metadata (set via `ctx.tag()`) |
| `source` | string | Source identifier, if applicable |
| `reason` | string | Reason string, if applicable |
| `status` | string | `"ok"` or error status |
| `elapsed_ms` | float | Wall-clock duration |
| `detail` | object | Action-specific payload (see below) |
| `metrics` | array | `MetricPoint` entries for this call |
| `provenance_chain` | array | Upstream provenance items, if traced |
| `created_at` | ISO 8601 | UTC timestamp |

**`detail` examples:**

```json
// add
{"ref": "contextseek://acme/bot/...", "item_id": "abc123", "stage": "knowledge"}

// retrieve
{"query": "backup procedure", "k": 10, "full": false, "hits": 7, "layer": "summary"}

// compact
{"dry_run": false, "merged": 3, "archived": 5, "evolved": 1}
```

### Reading the audit log in Python

```python
import json

records = []
with open(".contextseek/audit.jsonl") as f:
    for line in f:
        records.append(json.loads(line))

# All retrieve calls
retrieves = [r for r in records if r["action"] == "retrieve"]
avg_hits = sum(r["detail"]["hits"] for r in retrieves) / len(retrieves)
print(f"avg hits per retrieve: {avg_hits:.1f}")
```

Alternatively, use the in-memory `AuditLog` API:

```python
recent = ctx.audit_log.recent(limit=20, action="retrieve")
latencies = ctx.audit_log.metric_series("retrieve_latency_ms")
```

---

## Enriching records with `ctx.tag()`

Use `ctx.tag()` to attach `actor`, `request`, `source`, and `reason` to all audit records emitted inside the `with` block:

```python
with ctx.tag(
    actor={"user": "alice", "role": "admin"},
    request={"request_id": "req-001", "endpoint": "/answer"},
    reason="user query",
):
    response = ctx.retrieve("backup procedure", scope="acme/sre")
    ctx.add("new runbook step", scope="acme/sre", source="manual")
```

All records emitted during the block carry the actor and request fields. This is essential for answering *who did what* during an incident.

**Nesting `tag()` blocks is not supported** — the innermost `tag()` replaces the outer one. Wrap the entire logical operation in a single `tag()`.

---

## Prometheus metrics

Enable metrics export:

```env
OBSERVABILITY_METRICS_ENABLED=true
OBSERVABILITY_METRICS_PATH=.contextseek/metrics.prom
```

ContextSeek writes a Prometheus text file at `metrics_path` after every audited call. Scrape it with a Prometheus file-based exporter, or serve it from a custom endpoint.

The file follows the standard [Prometheus exposition format](https://prometheus.io/docs/instrumenting/exposition_formats/):

```
# TYPE contextseek_add_total counter
contextseek_add_total 42
# TYPE contextseek_retrieve_total counter
contextseek_retrieve_total 1337
# TYPE contextseek_retrieve_latency_ms_sum gauge
contextseek_retrieve_latency_ms_sum 8423.5
contextseek_retrieve_latency_ms_count 1337
...
```

### Available metrics

All metric names are prefixed with `contextseek_`:

| Metric | Type | Description |
|--------|------|-------------|
| `add_total` | counter | Total `add()` calls |
| `retrieve_total` | counter | Total `retrieve()` calls |
| `retrieve_hits_total` | counter | Total search hits returned |
| `compact_total` | counter | Total `compact()` calls |
| `dream_total` | counter | Total `dream()` calls |
| `feedback_total` | counter | Total `feedback()` calls |
| `forget_total` | counter | Total `forget()` calls |
| `delete_total` | counter | Total `delete()` calls |
| `{action}_latency_ms` | histogram | Per-call latency by action |

### Using `MetricsCollector` directly

```python
from contextseek.observability.metrics import MetricsCollector

collector = MetricsCollector()
collector.ingest_from_audit_log(ctx.audit_log)
print(collector.export_prometheus())
print(f"avg retrieve latency: {collector.get_avg('retrieve_latency_ms'):.1f} ms")
```

---

## What to monitor in production

**Key signals to alert on:**

| Signal | How to detect |
|--------|---------------|
| Retrieve hit count = 0 | `retrieve` detail: `hits == 0` repeatedly |
| High latency | `{action}_latency_ms` p95 > threshold |
| Repeated conflict errors | `add` status ≠ `"ok"` |
| Scope growth | `items` count rising without `compact()` runs |
| Dream/compact never running | Missing `dream` or `compact` audit entries |

**Recommended audit log rotation:** keep at most 30 days; archive older records to cold storage. The JSONL format is append-only and can be rotated with standard `logrotate` tooling.

---

## CLI metrics

```bash
contextseek metrics
```

Prints the current Prometheus text from the configured `metrics_path` file, or from in-memory counters if file metrics are disabled.

---

[← Storage](storage.md) · [Provenance & audit](provenance-and-audit.md) · [API reference](../reference/api.md)
