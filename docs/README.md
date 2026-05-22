# ContextSeek documentation

Public, **usage-oriented** documentation for integrating and operating ContextSeek.

## Languages

| Language | Entry |
|----------|--------|
| English | [docs/en/README.md](en/README.md) |
| 中文 | [docs/zh/README.md](zh/README.md) |

English and Chinese trees are **parallel** (same paths, translated content).

---

## Directory layout

```
docs/
├── README.md                 # This file — structure & conventions
├── en/                       # English user docs
│   ├── README.md
│   ├── getting-started/      # Install → first retrieve in <15 min
│   ├── concepts/             # Pure conceptual reference (new in 0.1.0)
│   │   ├── context-model.md
│   │   ├── scope-and-stage.md
│   │   └── retrieval-model.md
│   ├── guides/               # Task-oriented how-tos
│   │   └── integrations/     # DataPlugs, MCP/HTTP/CLI
│   ├── reference/            # API tables, env vars, examples index
│   └── troubleshooting.md
└── zh/                       # 中文用户文档（与 en/ 镜像）
    ├── README.md
    ├── getting-started/
    ├── concepts/
    ├── guides/
    │   └── integrations/
    ├── reference/
    └── troubleshooting.md
```

---

## Section purpose

### `getting-started/`

Onboarding only — no deep architecture.

| File | Audience goal |
|------|---------------|
| `installation.md` | pip/uv, extras (`http`, `langchain`, `oceanbase`) |
| `quickstart.md` | InMemory → file → `retrieve` / `expand` in one page |
| `configuration.md` | `.env`, `ContextSeekSettings`, phased LLM rollout |

### `concepts/`

Pure conceptual understanding — object model, isolation, retrieval architecture. No step-by-step procedures.

| File | Covers |
|------|--------|
| `context-model.md` | ContextItem fields, Provenance, Links, why unified |
| `scope-and-stage.md` | Scope design, Stage pipeline, Stability |
| `retrieval-model.md` | L0/L1/L2 tiers, recall routes, reranking pipeline |

### `guides/`

Task-based docs: "I want to …". No RFCs, no competitor comparisons.

| File | Covers |
|------|--------|
| `core-concepts.md` | Condensed overview linking to `concepts/` |
| `write-and-retrieve.md` | `add`, `retrieve`, `expand`, filters, `tools()` for agents |
| `provenance-and-audit.md` | `upstream`, `evidence_chain`, `tag`, forget/delete |
| `evolution.md` | `compact`, `dream`, `feedback`, `overview`, skills |
| `storage.md` | InMemory, File, OceanBase, tiered; when to pick which |
| `observability.md` | Audit log, Prometheus metrics, operational tips |

### `guides/integrations/`

Framework-specific wiring — keep each file self-contained.

| File | Covers |
|------|--------|
| `dataplugs.md` | DataPlugs (RAG, memory, trace); skill import |
| `mcp-http-cli.md` | MCP stdio/SSE, FastAPI routes, CLI commands |

### `reference/`

Lookup tables — minimal prose.

| File | Covers |
|------|--------|
| `api.md` | All `ContextSeek` methods, parameters, return types |
| `settings.md` | All environment variables with defaults |
| `examples.md` | Index of `examples/*.py` with one-line purpose |

### `troubleshooting.md`

Common issues and resolutions: install errors, empty results, evolution problems, OceanBase, debugging.

---

## Explicitly **out of scope** for `docs/`

- Internal architecture RFCs and design documents
- Product launch / marketing copy
- Contributor workflow — use `CONTRIBUTING.md` at repo root

---

## Conventions for authors

1. **One language per file** — no mixed EN/ZH in the same page.
2. **Relative links** — `../reference/api.md` within a language tree; cross-language links only from `docs/README.md`.
3. **Code must run** — snippets tested against current `ContextSeek` API.
4. **Secrets** — never commit real keys; reference `.env.example`.

---

## Suggested reading order

1. [Quickstart (EN)](en/getting-started/quickstart.md) · [快速上手 (ZH)](zh/getting-started/quickstart.md)
2. [ContextItem model](en/concepts/context-model.md) · [Scope & Stage](en/concepts/scope-and-stage.md)
3. [Write & retrieve](en/guides/write-and-retrieve.md)
4. [Evolution](en/guides/evolution.md) + [Observability](en/guides/observability.md)
5. [API reference](en/reference/api.md) when wiring production
