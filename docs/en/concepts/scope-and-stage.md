# Scope and Stage

Two of the most important attributes on a `ContextItem` are **scope** (where it belongs) and **stage** (how mature it is). Both affect storage, retrieval, and evolution behavior.

---

## Scope: your isolation boundary

Scopes are **path strings** with no enforced schema:

```
{tenant}/{project}/{subject}
```

| Scope | Meaning |
|-------|---------|
| `acme/checkout/user-42` | One shopper's agent memory |
| `acme/platform/on-call` | Shared runbooks for the platform team |
| `demo_tenant/default/alice` | Tutorial data |

`retrieve(scope=...)` searches that prefix and all sub-paths. There is no built-in "search all tenants" — call multiple scopes or funnel data into a shared scope via [DataPlugs](../guides/integrations/dataplugs.md).

### Best practices

- Use **stable IDs** in the last segment (`user-42`, `bot-7`), not display names that may change.
- Put **shared** knowledge in a team scope; do not replicate the same paragraph into thousands of user scopes.
- One logical agent session can use one scope per user; rotate scope only when you intentionally want a clean slate.

### Anti-patterns

| Don't | Why |
|-------|-----|
| `scope="session-" + uuid` per message | Nothing compounds; storage explodes |
| Secrets in `scope` | Scopes appear in logs and audit records |
| Mix unrelated products in one scope | Retrieval noise and policy risk |

---

## ScopeBuilder: standardized path construction

Hand-writing scope strings is error-prone. `ScopeBuilder` provides a chainable API where named methods make structure explicit:

```python
from contextseek import ScopeBuilder, ScopeTemplates

# Chainable build — each method returns a new instance (immutable, safe to branch)
scope = (
    ScopeBuilder()
    .org("acme")
    .project("payment-service")
    .agent("refund-agent")
    .build()
)
# → "acme/payment-service/refund-agent"

# run / task / user automatically prepend a type label
scope = (
    ScopeBuilder()
    .org("acme")
    .project("payment-service")
    .run("run_20260522_001")
    .build()
)
# → "acme/payment-service/run/run_20260522_001"

# Branch reuse — base is unaffected
base = ScopeBuilder().org("acme").project("pay")
scope_a = base.agent("refund").build()    # "acme/pay/refund"
scope_b = base.agent("checkout").build()  # "acme/pay/checkout"

# Build from environment variables (missing vars are silently skipped)
scope = ScopeBuilder.from_env(
    prefix="acme",
    env_vars={"project": "SERVICE_NAME", "run": "RUN_ID"},
).build()
```

### Preset templates

For common patterns, `ScopeTemplates` gives you a one-liner:

```python
from contextseek import ScopeTemplates

ScopeTemplates.org_knowledge("acme", "platform", "billing")
# → "acme/platform/knowledge/billing"

ScopeTemplates.agent_run("refund-agent", "r-001")
# → "agent/refund-agent/run/r-001"

ScopeTemplates.agent_run("refund-agent", "r-001", task_id="t-42")
# → "agent/refund-agent/run/r-001/task/t-42"

ScopeTemplates.user_space("u-99", "notes")
# → "user/u-99/notes"

ScopeTemplates.shared("payment-project", "knowledge")
# → "shared/payment-project/knowledge"
```

### Scope lint

Enable `scope_lint=True` during development — `ctx.add()` will emit a `ScopeLintWarning` whenever a scope looks malformed:

```python
from contextseek import ContextSeek
from contextseek.config.settings import ContextSeekSettings

ctx = ContextSeek.from_settings(ContextSeekSettings(scope_lint=True))
# These will trigger ScopeLintWarning:
ctx.add("...", scope="flat", source="test")          # no separator, recommend 2+ levels
ctx.add("...", scope="Acme/Pay", source="test")      # uppercase letters
ctx.add("...", scope="a/b/c/d/e/f/g", source="test") # more than 6 levels deep
```

See [Settings reference — SCOPE_LINT](../reference/settings.md) for the full rule set.

### Scope analysis

After writing data, inspect the current structure with `ctx.scope_tree()` and `ctx.scope_stats()`:

```python
# Print a scope hierarchy tree (item / knowledge / skill counts per scope)
tree = ctx.scope_tree(root="acme")
tree.print()
# acme/
#   payment-service/
#     refund/   (142 items, 38 knowledge, 5 skills)
#     checkout/ (891 items, 12 knowledge)

# Aggregate stats for one scope
stats = ctx.scope_stats("acme/payment-service/refund")
print(stats.item_count, stats.avg_confidence)
```

See [API reference — Scope analysis](../reference/api.md#scope-analysis) for full details.

---

## Stage: maturity pipeline

```
raw  →  extracted  →  knowledge  →  skill
```

| Stage | Typical inputs | Default confidence weight in hits |
|-------|----------------|-----------------------------------|
| `raw` | Chat turns, tool JSON, fresh traces | 0.3 |
| `extracted` | Miner output, single-step insights | 0.6 |
| `knowledge` | Merged facts, validated runbooks | 0.85 |
| `skill` | Executable playbooks | 1.0 |

**Automatic inference:** if you omit `stage` on `add()`, ContextSeek infers it from `source_type` and content shape. With `EVOLUTION_LLM_STAGE_INFER_ENABLED=true`, an LLM classifier may override heuristics.

**Overriding at write time:**

```python
from contextseek.domain.stages import Stage

# Force a document directly to knowledge
ctx.add("team runbook", scope="acme/sre", source="wiki", stage=Stage.knowledge)
```

**Evolution:** `compact()` promotes `extracted` clusters to `knowledge`. `dream()` generates speculative `extracted` items at idle time. See [Evolution](../guides/evolution.md) for details.

---

## Stability

Stability controls how long an item is retained before decay or archival:

| Value | Meaning | Typical stage |
|-------|---------|---------------|
| `ephemeral` | Expires with the session or task | `raw` (tool calls, temp state) |
| `transient` | Default for raw/extracted; normal decay | `raw`, `extracted` |
| `stable` | Long-lived knowledge | `knowledge` |
| `permanent` | Skills and critical policies; manual delete only | `skill` |

Default stability per stage is determined automatically by ContextSeek. Override on `add()`:

```python
from contextseek.domain.stages import Stability

ctx.add("permanent policy", scope="acme/legal", source="policy-doc",
        stability=Stability.permanent)
```

---

## Design goal: one object, three guarantees

Every record entering ContextSeek is expected to be:

| Guarantee | Mechanism |
|-----------|-----------|
| **Retrievable** | Index on write; `retrieve()` with recall + rerank |
| **Traceable** | Mandatory `provenance`; `links`; audit APIs |
| **Evolvable** | `stage` pipeline; `compact()` / `dream()` |

Data without an identifiable source, data that will never be searched, or throwaway buffers should stay outside ContextSeek (Redis session cache, raw log files, etc.).

---

## Next steps

- [Context model](context-model.md) — ContextItem fields, Provenance, Links
- [Retrieval model](retrieval-model.md) — L0/L1/L2 tiers and search pipeline
- [Evolution](../guides/evolution.md) — `compact()`, `dream()`, `feedback()`
