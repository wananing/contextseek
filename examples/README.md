# Examples

## 1) Full pipeline with FileBackend

```bash
uv run python examples/full_pipeline_file.py
```

Demonstrates:
- FileBackend local file storage (zero external deps)
- Adding ContextItems with different source types
- `retrieve(kind=hits)` keyword-style ranked hits
- RetrievalOrchestrator for low-level retrieval control

## 2) Full pipeline with OceanBase

```bash
uv run python examples/full_pipeline_ob.py
```

Demonstrates:
- OceanBase as vector + full-text hybrid backend
- LangChain embedder integration
- Semantic `retrieve(kind=hits)` with hybrid recall

## 3) LangChain bridges

```bash
PYTHONPATH=src python examples/langchain_pipeline.py
```

Demonstrates:
- `ContextSeekMemory` for chat history persistence
- `ContextSeekRetriever` for context retrieval
- LangChain adapter usage (not DataPlugs)

## 4) Research Agent Demo (comprehensive)

```bash
uv run python examples/research_agent_demo.py
```

Showcases all ContextSeek capabilities:
- ContextItem with multiple source types and provenance
- Links between items (supports/refutes/supersedes)
- Evolution pipeline (raw → extracted → knowledge → skill)
- `retrieve(kind=hits)` vs `retrieve(kind=context)` (ranked vs budgeted)
- Trace ingestion and training data export
- Strategy routing with canary rules
- Context injection for LLM prompts
- Skill execution framework

## 5) PowerMem integration

**Only need memories?** Keep using PowerMem `memory.add` / `memory.search` — ContextSeek is optional.

**Need memories + trace/RAG/playbook in one `retrieve()`?** Plug then query ContextSeek:

```python
from contextseek.plugs import PowerMemPlug

ctx.plug(
    PowerMemPlug.from_memory(memory, user_id="...", agent_id="..."),
    scope="tenant/bot/user",
)
hits = ctx.retrieve(query, scope="tenant/bot/user")
```

Minimal example:

```bash
uv run python examples/powermem_minimal.py
```

Full DataPlug walkthrough:

```bash
uv run python examples/powermem_plug_demo.py
```

Demonstrates:
- ContextSeek as a **DataPlug socket**: `PowerMemPlug` imports PowerMem `get_all` rows
- `PowerMemPlug.from_records()` — normalize PowerMem search/get_all dicts
- Same-scope unified `retrieve()` over PowerMem memories + ContextSeek-native knowledge
- Provenance (`powermem://<id>`) and `powermem` tags for filtering

Optional live PowerMem (requires `pip install powermem` or sibling repo on `PYTHONPATH`):

```bash
USE_POWERMEM=live uv run python examples/powermem_plug_demo.py
```

## 6) HTTP API

Start API server:

```bash
uvicorn contextseek.http.server:app --host 127.0.0.1 --port 8000 --reload
```

Example requests:

```bash
curl -X POST http://127.0.0.1:8000/add \
  -H "Content-Type: application/json" \
  -d '{"content": "hello", "scope": "t/p/u", "source": "curl"}'

curl -X POST http://127.0.0.1:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "hello", "scope": "t/p/u", "k": 5}'
```

Endpoints: `/add`, `/retrieve`, `/expand`, `/compact`, `/forget`, `/delete`, `/health`

## 7) Real LLM + OceanBase full pipeline

Run:

```bash
uv run python examples/llm_full_pipeline_oceanbase.py
```

What it covers:
- Real LLM calls with OceanBase backend
- Phase 1/2/3 LLM features end-to-end
- Prompt-template override via `PromptSettings` (`PROMPT_*`)
- Retrieval, compact/evolution, dream, feedback, and skill inspection
