<p align="center">
  <img src="Images/app-icon.svg" alt="Cognitive DAG Agent" width="96" height="96"/>
</p>

<h1 align="center">Cognitive DAG Agent</h1>

<p align="center">
  <strong>Planner → Skills → Critic → Formatter</strong><br/>
  Parallel fan-out · Tool-grounded critic · Coder sandbox · Live DAG graph
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#web-ui">Web UI</a> ·
  <a href="#demo-queries">Demo queries</a> ·
  <a href="#eval-results">Eval results</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#tests">Tests</a>
</p>

**DAG orchestrator:** the Planner emits a skill graph; the Executor runs every ready node in parallel (`asyncio.gather`); graphs and per-node state persist under `state/sessions/`. Default mode is **`AGENT_MODE=dag`** (set `loop` in `.env` for the iteration-loop agent).

**Problem domain:** multi-step tasks with explicit parallelism (city populations), tool-verified critic gates (JSON keys), sandbox-backed arithmetic (coder), and a **calculator** skill — all without per-skill Executor changes.

## Quick start

**Requires:** `uv`, Python 3.12+, **`GEMINI_API_KEY`** in `.env` (see [`.env.example`](.env.example)).

```bash
uv sync
cp .env.example .env   # add GEMINI_API_KEY
./scripts/serve.sh
```

Open **http://127.0.0.1:8080/**

CLI:

```bash
uv run python scripts/dag/run_query.py hello
uv run python scripts/dag/run_query.py --query "Say hello."
uv run python scripts/dag/run_query.py --resume dag_K_<timestamp>

# Full demo eval → logs/dag/<id>.log + summary.json
uv run python scripts/dag/run_eval.py --fresh
uv run python scripts/dag/run_eval.py --fresh --ids hello A I J K P C_pass C_fail M CALC
```

Optional gateway (instructor `llm_gatewayV8`, port **8108**):

```bash
# .env — DAG uses GATEWAY_V8_URL only (not GATEWAY_URL / 8107)
GATEWAY_V8_URL=http://127.0.0.1:8108
```

Pins: [`agent_routing.yaml`](agent_routing.yaml). Without it, `SkillLLMClient` calls Gemini directly.

## Web UI

| Area | What it does |
|------|----------------|
| **Chat** | Run any query; streams `[dag]` trace and final answer |
| **DAG Queries** | Ten built-in demo queries (five capability groups). **Design blocks** at the top explain parallel fan-out (**P**) and critic pass/fail (**C_pass** / **C_fail**); cards load verbatim text and run |
| **Graph** | Full-width **vis-network** view: canvas + sidebar (session stats, node detail on click, FAISS memory hits at run start). Session picker, Refresh, Fit, optional auto-refresh during a live run |
| **Documents** | Upload / bulk-index `research_papers/` or `papers/` (RAG corpus for retriever) |
| **RAG** | Custom recall queries (iteration-loop corpus; optional) |

Graph API (used by the UI):

- `GET /api/dag/sessions` — recent sessions (newest first)
- `GET /api/dag/graph?session_id=` — nodes/edges, `stats` (status counts), `memory_hits` (snapshotted at session start)

Live runs emit `[UI_SESSION_JSON] {"session_id": "..."}` so the graph tab can follow the active session.

## Demo

**[YouTube demo →](https://youtu.be/YOUR_LINK)** — replace after recording the capability groups below (checklist in [docs/ASSIGNMENT.md](docs/ASSIGNMENT.md)).

## Demo queries

Full verification commands: **[docs/ASSIGNMENT.md](docs/ASSIGNMENT.md)**  
Corpus (verbatim queries + bounds): [`corpus/dag/ASSIGNMENT.json`](corpus/dag/ASSIGNMENT.json)

| Group | Query ids | What it proves |
|-------|-----------|----------------|
| **Base** | `hello`, `A`, `I`, `J`, `K` | Minimum DAG, Shannon fetch, parallel populations, graceful fail, resume |
| **Parallel** | `P` | ≥3 concurrent researchers; wall-clock ≈ max branch, not sum |
| **Critic** | `C_pass`, `C_fail` | `validate_json_keys` pass; fail → recovery planner |
| **Coder** | `M` | `prompts/coder.md` → SandboxExecutor; answer **150769** |
| **Calculator** | `CALC` | **calculator** + `safe_calculate` (yaml + prompt only) |

**Parallel fan-out (design query P):** Planner must emit ≥3 independent researcher nodes in one wave. After the run:

```bash
uv run python scripts/dag/analyze_session_timing.py dag_P_<timestamp> --json
# expect parallel_confirmed=true; layer wall ≈ max(branch), not sum
```

Same shape as base query **I** (London / Paris / Berlin).

**Critic verdict (C_pass then C_fail):** Property verified with `validate_json_keys` (`author`, `title`, `year`). Run both queries; on **C_fail** the session graph must show a recovery planner node after critic failure (inspect in the **Graph** tab).

### Eval results

Reproduce locally with `uv run python scripts/dag/run_eval.py --fresh`. Logs: `logs/dag/<id>.log` · combined `logs/dag/summary.json` · traces: `state/sessions/<session_id>/` (includes `memory_hits.json` when FAISS priming ran).

| Group | Id | Log | Status | Wall (s) | Bound (s) | Notes |
|-------|-----|-----|--------|----------|-----------|-------|
| Base | hello | [`logs/dag/hello.log`](logs/dag/hello.log) | ok | 12.6 | 15 | 2-node DAG (planner → formatter) |
| Base | A | `logs/dag/A.log` | — | — | 180 | Run eval to generate |
| Base | I | `logs/dag/I.log` | — | — | 120 | Canonical parallel fan-out (3 researchers) |
| Base | J | [`logs/dag/J.log`](logs/dag/J.log) | ok | 9.6 | 30 | Fail-fast planner → formatter |
| Base | K | `logs/dag/K.log` | — | — | 180 | Requires kill + `--resume` demo |
| Parallel | P | `logs/dag/P.log` | — | — | 120 | + `analyze_session_timing.py` |
| Critic | C_pass | [`logs/dag/C_pass.log`](logs/dag/C_pass.log) | ok | 40.1 | 60 | Critic pass (`validate_json_keys`) |
| Critic | C_fail | `logs/dag/C_fail.log` | — | — | 90 | Critic fail → recovery planner |
| Coder | M | [`logs/dag/M.log`](logs/dag/M.log) | ok | 21.3 | 60 | Answer **150769** |
| Calculator | CALC | [`logs/dag/CALC.log`](logs/dag/CALC.log) | ok | 24.0 | 45 | Calculator skill |

Structural shapes (no live LLM): `tests/test_worked_queries.py`. Recovery classifier: `tests/test_recovery.py`.

## Architecture

```
USER_QUERY
    │
    ▼
┌─────────┐     extends graph      ┌──────────────────────────────┐
│ Planner │ ─────────────────────► │ researcher × N (parallel)    │
│ (skill) │                        │ distiller → critic → formatter│
└─────────┘                        │ coder → sandbox_executor      │
                                   │ calculator → formatter        │
                                   └──────────────────────────────┘
```

| Component | Location |
|-----------|----------|
| Graph + Executor + `DagAgent` | `cognitive_dag/flow.py` |
| Graph viz (API / UI) | `cognitive_dag/graph_viz.py` |
| Skill catalogue | `agent_config.yaml` + `prompts/*.md` |
| Critic splice | Auto on `distiller` out-edges (`critic: true`) |
| Recovery | `cognitive_dag/recovery.py` → `classify_failure` |
| Persistence | `state/sessions/<sid>/` (`graph.json`, `nodes/*.json`, `query.txt`, `memory_hits.json`) |
| LLM | Gemini SDK default; optional `GATEWAY_V8_URL` |

**Rules:** new skill = yaml + prompt only; Planner emits the graph; touching Executor for non-generic behavior is a bug.

## Project layout

```
├── cognitive_dag/
│   ├── flow.py              # Graph, Executor, DagAgent (UI + CLI)
│   ├── graph_viz.py         # NetworkX → vis-network payload + memory_hits/stats
│   ├── persistence.py       # Atomic session store, resume, memory_hits.json
│   ├── recovery.py          # Failure classifier + critic recovery
│   ├── skills.py            # SkillRegistry + MEMORY HITS in prompts
│   ├── sandbox.py           # SandboxExecutor subprocess runner
│   ├── mcp_server.py        # validate_json_keys, safe_calculate, RAG tools, …
│   └── memory.py, action.py, agent.py, …
├── prompts/                 # planner, researcher, critic, coder, calculator, …
├── agent_config.yaml
├── agent_routing.yaml       # Optional gateway provider pins
├── app.py                   # FastAPI + /api/dag/*
├── templates/index.html     # Chat, DAG Queries (design blocks), Graph, Documents
├── corpus/dag/ASSIGNMENT.json   # Demo query corpus + design_queries metadata
├── scripts/dag/             # run_eval, run_query, analyze_session_timing
├── docs/ASSIGNMENT.md       # Detailed verification guide
├── docs/DEFERRALS.md
├── logs/dag/                # Eval logs (gitignored)
├── state/sessions/          # Persisted DAG runs (gitignored)
└── tests/
```

## Tests

```bash
uv sync --extra dev
env -u VIRTUAL_ENV uv run pytest -q
```

Focused DAG suite:

```bash
uv run pytest tests/test_dag_flow.py tests/test_recovery.py tests/test_worked_queries.py \
  tests/test_dag_mcp_tools.py tests/test_assignment_spec.py tests/test_graph_viz.py \
  tests/test_sandbox.py -q
```

Architecture smoke (RAG submission gates):

```bash
uv run python tests/test_architecture.py
```

## Optional: document RAG

FAISS memory is primed once per DAG run (`memory.read` at session start), snapshotted to `memory_hits.json`, and rendered into every skill prompt. Index from the **Documents** tab or:

```bash
uv run python scripts/download_research_papers.py --from-disk
uv run python scripts/index_research_corpus.py
```

Design simplifications and forward pointers: [docs/DEFERRALS.md](docs/DEFERRALS.md)

## Tech

Python 3.12 · uv · FastAPI · NetworkX · vis-network · Gemini SDK · MCP stdio · FAISS · asyncio
