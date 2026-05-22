# Context Evolution

ContextSeek items don't stay static. They mature through a stage pipeline (`raw → extracted → knowledge → skill`) and can be consolidated, synthesized, and distilled over time. This guide covers the four evolution controls: `compact()`, `dream()`, `feedback()`, and `overview()`.

---

## The stage pipeline

Every `ContextItem` has a `stage` that reflects its maturity:

| Stage | Meaning | Typical source |
|-------|---------|----------------|
| `raw` | Unprocessed observation | Trace, agent log, user input |
| `extracted` | Cleaned and structured | Post-processing, dream synthesis |
| `knowledge` | Validated, stable fact | Document ingestion, merge output |
| `skill` | Executable procedure | Distilled from high-use knowledge |

Stage advances automatically through `compact()`. You can also override stage on `add()`:

```python
from contextseek.domain.stages import Stage

ctx.add("deploy runbook step 3", scope="acme/sre", source="wiki",
        stage=Stage.knowledge)
```

---

## `compact()` — the evolution pipeline

`compact()` is the main housekeeping operation. Run it periodically or after large ingestion batches.

```python
report = ctx.compact(scope="acme/bot/user_42")
print(f"merged={report.merged_count}, archived={report.archived_count}, evolved={report.evolved_count}")
```

**What it does:**

When `EVOLUTION_ENABLED=false` (default): hash-based exact deduplication only.

When `EVOLUTION_ENABLED=true`, the full pipeline runs in order:

1. **Hash dedup** — exact duplicate items are soft-deleted
2. **Extract** — `raw` items older than `EVOLUTION_EXTRACT_MIN_AGE_SECONDS` are promoted to `extracted`
3. **Semantic merge** — `extracted` items with cosine similarity ≥ `EVOLUTION_SEMANTIC_MERGE_THRESHOLD` are clustered; clusters ≥ `EVOLUTION_MIN_CLUSTER_SIZE` are merged into a new `knowledge` item
4. **Distill** — `knowledge` items with `access_count ≥ EVOLUTION_DISTILL_MIN_USE_COUNT` and `relevance_boost ≥ EVOLUTION_DISTILL_MIN_RELEVANCE_BOOST` are candidates for skill distillation
5. **Archive** — ephemeral items past `EVOLUTION_EPHEMERAL_TTL_SECONDS` and low-importance stale items are soft-archived

**Dry run:**

```python
preview = ctx.compact(scope="acme/bot/user_42", dry_run=True)
print(f"would merge {preview.merged_count} items")
```

**Recommended schedule:** run `compact()` nightly or after significant write activity. Pair with `overview()` to decide if compaction is needed.

---

## `dream()` — idle-time synthesis

`dream()` runs two creative passes at idle time:

- **Consolidation** — finds recurring patterns across many items in the scope and synthesizes new `extracted` items representing those patterns
- **Divergence** — generates hypotheses bridging two dissimilar clusters, creating new speculative items with low confidence

Dream items are tagged `dream:consolidation` or `dream:divergence`, start at `Stage.extracted`, and carry low confidence. They decay unless reinforced by `feedback()`.

```python
report = ctx.dream(scope="acme/bot/user_42")
print(f"generated {report.total_dream_items} dream items "
      f"({len(report.consolidation.items)} consolidation, "
      f"{len(report.divergence.items) if report.divergence else 0} divergence)")
```

**When to run:** after large write batches, or on a scheduler during off-peak hours. Do not run `dream()` on every request.

**LLM mode:** set `DREAM_LLM_ENABLED=true` for richer synthesis. Without it, dream uses keyword-overlap heuristics.

```python
# Dry run — inspect without persisting
preview = ctx.dream(scope="acme/bot/user_42", dry_run=True)
```

---

## `feedback()` — steer retrieval and evolution

`feedback()` provides explicit relevance signal from agents or users:

```python
# Positive feedback: item was useful
ctx.feedback(hit.item.ref, scope="acme/bot", score=0.8, reason="exactly right")

# Negative feedback: item was not useful
ctx.feedback(hit.item.ref, scope="acme/bot", score=-0.5, reason="outdated")
```

**Score mechanics:**

| Score range | Effect |
|-------------|--------|
| `> 0` | Raises `relevance_boost` (max 5.0); increments `access_count`; tags item `"evolution_candidate"` when boost ≥ 2.0 |
| `< 0` | Lowers `relevance_boost` (min 0.1); tags `raw`/`extracted` items `"needs_review"`; score ≤ −0.5 decays `importance` |

`relevance_boost` is a score multiplier in the heuristic reranker. Items with high `access_count` + `relevance_boost` become distillation candidates sooner.

**LLM reason parsing:** set `EVOLUTION_LLM_FEEDBACK_ENABLED=true` to parse the `reason` string for structured signals (e.g., "outdated" → flag for review; "very helpful" → accelerate promotion).

---

## `overview()` — scope health check

`overview()` is a read-only scan that tells you what's in a scope without modifying anything:

```python
report = ctx.overview(scope="acme/bot")
print(report)
```

The report includes:
- Item counts per stage (`raw`, `extracted`, `knowledge`, `skill`)
- Items ready for extraction
- Items pending convergence / merge
- Items eligible for distillation

Use `overview()` before running `compact()` to decide if it's worth it, or to monitor scope health in dashboards.

---

## `execute_skill()` — run a distilled skill

When an item reaches `Stage.skill` it can be executed directly:

```python
from contextseek.domain.stages import Stage

skills = ctx.items(scope="acme/bot", stage=Stage.skill)
for skill in skills:
    result = ctx.execute_skill(skill.ref, scope="acme/bot",
                               inputs={"query": "backup procedure"})
    print(result.output)
```

Skills can be of type `"prompt"` (returns an LLM-rendered string), `"tool"` (returns a tool call spec), or `"mcp"` (returns an MCP call spec).

See `skill_tools()` and `skill_context()` in the [API reference](../reference/api.md) for exporting skills as LLM tool definitions.

---

## Recommended workflow

```
Daily / after large ingestion:
    ctx.overview(scope=...)    # check health
    ctx.compact(scope=...)     # dedupe + evolve

Off-peak / weekly:
    ctx.dream(scope=...)       # pattern synthesis

Inline / agent loop:
    ctx.feedback(ref, ...)     # after every retrieve/use
```

### Minimal config to enable evolution

```env
EVOLUTION_ENABLED=true

# Recommended Phase 1 LLM additions:
RETRIEVAL_RERANKER_MODE=llm
DREAM_LLM_ENABLED=true
```

See [Phased LLM rollout](../getting-started/configuration.md#phased-llm-rollout) before enabling all `EVOLUTION_LLM_*` flags at once.

---

[← Write & retrieve](write-and-retrieve.md) · [Provenance & audit](provenance-and-audit.md) · [API reference](../reference/api.md)
