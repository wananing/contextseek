# 可观测性

ContextSeek 提供两个可观测性数据流：**审计日志**（JSONL 格式，每次 API 调用一条记录）和 **Prometheus 兼容指标**（导出为文本文件）。两者默认均关闭。

---

## 审计日志

在 `.env` 中启用审计日志：

```env
OBSERVABILITY_AUDIT_ENABLED=true
OBSERVABILITY_AUDIT_PATH=.contextseek/audit.jsonl
```

每次调用 `add()`、`retrieve()`、`compact()`、`dream()`、`feedback()`、`forget()`、`delete()` 和 `evidence_chain()` 时，都会向文件追加一行 JSON。

### 记录结构

每行是一个 JSON 对象，包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `request_id` | string | 每次调用自动生成的 UUID |
| `action` | string | API 方法名：`add`、`retrieve`、`compact` 等 |
| `scope` | string | 本次操作的 scope |
| `policy_version` | string | 策略版本标签（来自 `pin()`） |
| `actor` | object | 调用者身份（通过 `ctx.tag()` 设置） |
| `request` | object | 请求元数据（通过 `ctx.tag()` 设置） |
| `source` | string | 来源标识（如适用） |
| `reason` | string | 原因字符串（如适用） |
| `status` | string | `"ok"` 或错误状态 |
| `elapsed_ms` | float | 实际耗时（毫秒） |
| `detail` | object | 操作专属载荷（见下方示例） |
| `metrics` | array | 本次调用的 `MetricPoint` 条目 |
| `provenance_chain` | array | 上游 Provenance 条目（如已追踪） |
| `created_at` | ISO 8601 | UTC 时间戳 |

**`detail` 示例：**

```json
// add
{"ref": "contextseek://acme/bot/...", "item_id": "abc123", "stage": "knowledge"}

// retrieve
{"query": "备份流程", "k": 10, "full": false, "hits": 7, "layer": "summary"}

// compact
{"dry_run": false, "merged": 3, "archived": 5, "evolved": 1}
```

### 在 Python 中读取审计日志

```python
import json

records = []
with open(".contextseek/audit.jsonl") as f:
    for line in f:
        records.append(json.loads(line))

# 所有 retrieve 调用
retrieves = [r for r in records if r["action"] == "retrieve"]
avg_hits = sum(r["detail"]["hits"] for r in retrieves) / len(retrieves)
print(f"平均命中数：{avg_hits:.1f}")
```

也可使用内存中的 `AuditLog` API：

```python
recent = ctx.audit_log.recent(limit=20, action="retrieve")
latencies = ctx.audit_log.metric_series("retrieve_latency_ms")
```

---

## 使用 `ctx.tag()` 丰富审计记录

使用 `ctx.tag()` 将 `actor`、`request`、`source`、`reason` 附加到 `with` 块内所有操作的审计记录中：

```python
with ctx.tag(
    actor={"user": "alice", "role": "admin"},
    request={"request_id": "req-001", "endpoint": "/answer"},
    reason="用户查询",
):
    response = ctx.retrieve("备份流程", scope="acme/sre")
    ctx.add("新运维步骤", scope="acme/sre", source="manual")
```

块内所有审计记录都会携带 actor 和 request 字段。这对于故障排查时还原"谁做了什么"至关重要。

**不支持嵌套 `tag()` 块** — 内层 `tag()` 会覆盖外层。将整个逻辑操作包裹在一个 `tag()` 内。

---

## Prometheus 指标

启用指标导出：

```env
OBSERVABILITY_METRICS_ENABLED=true
OBSERVABILITY_METRICS_PATH=.contextseek/metrics.prom
```

ContextSeek 在每次被审计的调用后将 Prometheus 文本写入 `metrics_path` 文件。可用 Prometheus 文件 exporter 采集，或从自定义 HTTP 端点提供。

文件格式符合标准 [Prometheus 文本格式](https://prometheus.io/docs/instrumenting/exposition_formats/)：

```
# TYPE contextseek_add_total counter
contextseek_add_total 42
# TYPE contextseek_retrieve_total counter
contextseek_retrieve_total 1337
# TYPE contextseek_retrieve_latency_ms_sum gauge
contextseek_retrieve_latency_ms_sum 8423.5
contextseek_retrieve_latency_ms_count 1337
```

### 可用指标

所有指标名以 `contextseek_` 为前缀：

| 指标 | 类型 | 说明 |
|------|------|------|
| `add_total` | counter | `add()` 调用总次数 |
| `retrieve_total` | counter | `retrieve()` 调用总次数 |
| `retrieve_hits_total` | counter | 检索命中总数 |
| `compact_total` | counter | `compact()` 调用总次数 |
| `dream_total` | counter | `dream()` 调用总次数 |
| `feedback_total` | counter | `feedback()` 调用总次数 |
| `forget_total` | counter | `forget()` 调用总次数 |
| `delete_total` | counter | `delete()` 调用总次数 |
| `{action}_latency_ms` | histogram | 各操作的单次耗时 |

### 直接使用 `MetricsCollector`

```python
from contextseek.observability.metrics import MetricsCollector

collector = MetricsCollector()
collector.ingest_from_audit_log(ctx.audit_log)
print(collector.export_prometheus())
print(f"平均 retrieve 延迟：{collector.get_avg('retrieve_latency_ms'):.1f} ms")
```

---

## 生产环境监控建议

**关键告警信号：**

| 信号 | 检测方式 |
|------|----------|
| retrieve 命中数持续为 0 | `retrieve` detail 中 `hits == 0` 反复出现 |
| 高延迟 | `{action}_latency_ms` p95 超过阈值 |
| 重复写入冲突错误 | `add` 的 `status ≠ "ok"` 频繁出现 |
| Scope 无限增长 | `items` 数量持续上涨而未执行 `compact()` |
| Dream/compact 长期未运行 | 审计日志中缺少 `dream` 或 `compact` 记录 |

**审计日志轮转建议：** 保留最近 30 天，更早的记录归档到冷存储。JSONL 格式为追加写入，可用标准 `logrotate` 工具轮转。

---

## CLI 指标

```bash
contextseek metrics
```

打印当前 Prometheus 文本（来自配置的 `metrics_path` 文件，或在文件指标禁用时来自内存计数器）。

---

[← 存储后端](storage.md) · [溯源与审计](provenance-and-audit.md) · [API 参考](../reference/api.md)
