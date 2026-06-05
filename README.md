<p align="center">
  <img src="Images/app-icon.svg" alt="Cognitive DAG Agent" width="96" height="96"/>
</p>

<h1 align="center">Cognitive DAG Agent</h1>

<p align="center">
  <strong>Planner → Skills → Critic → Formatter</strong><br/>
  Parallel fan-out · Tool-grounded critic · Coder sandbox · Live DAG graph
</p>

<p align="center">
  <a href="#whats-new">What's new</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#web-ui">Web UI</a> ·
  <a href="#demo-queries">Demo queries</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#tests">Tests</a>
</p>

**DAG orchestrator:** the Planner emits a skill graph; the Executor runs every ready node in parallel (`asyncio.gather`); graphs and per-node state persist under `state/sessions/`. Default mode is **`AGENT_MODE=dag`** (set `loop` in `.env` for the iteration-loop agent).

## What's new

This repo is **Session 8**: a **graph DAG agent** built on top of the Session 7 iteration-loop stack (same RAG corpus, MCP tools, and Gemini path). The default runtime is no longer “think → act → repeat in one thread” — it is **plan once (or replan on failure), fan out skills in parallel, persist every node to disk**.

### vs a regular iteration-loop agent


|               | **Iteration loop** (`AGENT_MODE=loop`)                   | **DAG agent** (`AGENT_MODE=dag`, default)                                         |
| ------------- | -------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Control flow  | Linear history: Perception → Decision → Action each turn | **NetworkX graph** that grows at runtime                                          |
| Parallelism   | Mostly sequential tool calls                             | **`asyncio.gather`** on every ready wave                                          |
| State         | Conversation + memory items                              | **`state/sessions/<id>/`** — `graph.json`, `nodes/*.json`, `query.txt`            |
| Recovery      | Retry inside the same loop                               | **Critic fail → recovery Planner** splices new nodes; **Stop / Resume** from disk |
| Observability | Live console trace                                       | Trace **plus** live **Graph** tab (status colours, session stats, memory hits)    |


### vs “RAG then answer”

RAG here is **primed once per DAG session** (`memory_hits.json` + FAISS), then injected into skill prompts — not a single retrieve-and-synthesize hop. The **Planner** chooses skills: `retriever` for indexed corpus, **`researcher` for explicit URLs** (memory hits do not replace a named `fetch_url`), `distiller` for structured extraction. Token use is **scoped per node**, not one ever-growing chat.

### New in this project

- **Live DAG graph** — incremental SVG updates, auto-refresh during runs, node detail sidebar, PNG export
- **Cursor-style Stop** — cancel in-flight work; running nodes → `pending` on disk for checkpoint resume
- **SIGKILL resume** — `run_query.py --resume <session_id>` or Graph tab **Resume**; completed upstream stays done
- **Tool-grounded Critic** — auto-spliced after `distiller`; `validate_json_keys` / `count_syllables`; fail triggers replan
- **Coder + SandboxExecutor** — Python verified in a subprocess; formatter quotes sandbox stdout, not guessed math
- **Skill catalogue** — add skills via `agent_config.yaml` + `prompts/*.md` only (`calculator`, **`prosody_analyst`**); no Executor fork per skill
- **Assignment corpus** — ten demo queries (parts 1–5) with design blocks and wall-clock bounds ([`corpus/dag/ASSIGNMENT.json`](corpus/dag/ASSIGNMENT.json))
- **Parallel timing proof** — `scripts/dag/analyze_session_timing.py` confirms wall-clock ≈ **max(branch)**, not sum

Deferred production upgrades (hybrid RRF, semantic chunking, mmap FAISS) are documented in [docs/DEFERRALS.md](docs/DEFERRALS.md) — the demo stack is intentionally dense-retrieval + heuristic chunking end-to-end.

## Quick start

**Requires:** `uv`, Python 3.12+, **`GEMINI_API_KEY`** in `.env` (see [`.env.example`](.env.example)).

```bash
uv sync
cp .env.example .env   # add GEMINI_API_KEY
./scripts/serve.sh
```

Open **[http://127.0.0.1:8080/](http://127.0.0.1:8080/)**

CLI:

```bash
uv run python scripts/dag/run_query.py hello
uv run python scripts/dag/run_query.py --query "Say hello."
uv run python scripts/dag/run_query.py --resume dag_K_<timestamp>

# Run all assignment queries (batch eval)
uv run python scripts/dag/run_eval.py --fresh
uv run python scripts/dag/run_eval.py --fresh --ids hello A I J K P C_pass C_fail M PROS
```

Optional gateway (instructor `llm_gatewayV8`, port **8108**):

```bash
# .env — DAG uses GATEWAY_V8_URL only (not GATEWAY_URL / 8107)
GATEWAY_V8_URL=http://127.0.0.1:8108
```

Pins: [`agent_routing.yaml`](agent_routing.yaml). Without it, `SkillLLMClient` calls Gemini directly.

## Web UI


| Area            | What it does                                                                                                                                                                                                             |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Chat**        | Run any query; streams `[dag]` trace and final answer                                                                                                                                                                    |
| **DAG Queries** | Submission order parts **1–5**: base (`hello`–`K`) → parallel (`P`) → critic (`C_pass`/`C_fail`) → coder (`M`) → prosody analyst (`PROS`). Design requirements inline before parts 2–3; cards load verbatim text and run |
| **Graph**       | Full-width **vis-network** view: canvas + sidebar (session stats, node detail on click, FAISS memory hits at run start). Session picker, Refresh, Fit, optional auto-refresh during a live run                           |
| **Documents**   | Upload / bulk-index `research_papers/` or `papers/` (RAG corpus for retriever)                                                                                                                                           |
| **RAG**         | Custom recall queries (iteration-loop corpus; optional)                                                                                                                                                                  |


Graph API (used by the UI):

- `GET /api/dag/sessions` — recent sessions (newest first)
- `GET /api/dag/graph?session_id=` — nodes/edges, `stats` (status counts), `memory_hits` (snapshotted at session start)

Live runs emit `[UI_SESSION_JSON] {"session_id": "..."}` so the graph tab can follow the active session.

## Demo

**[YouTube demo →](https://youtu.be/YOUR_LINK)** — replace after recording the capability groups below (checklist in [docs/ASSIGNMENT.md](docs/ASSIGNMENT.md)).

## Demo queries

Full verification commands: **[docs/ASSIGNMENT.md](docs/ASSIGNMENT.md)**  
Corpus (verbatim queries + bounds): [`corpus/dag/ASSIGNMENT.json`](corpus/dag/ASSIGNMENT.json)


| Part  | Assignment requirement                                                            | Query ids                   | Screenshots        |
| ----- | --------------------------------------------------------------------------------- | --------------------------- | ------------------ |
| **1** | Pass five base queries verbatim, within iteration and wall-clock bounds           | `hello`, `A`, `I`, `J`, `K` | `Images/DAG/1`–`5` |
| **2** | Parallel fan-out: ≥3 independent sub-tasks; wall-clock ≈ **max(branch)**, not sum | `P`                         | `Images/DAG/6`     |
| **3** | Critic verdict: tool-verified pass **and** fail; fail splices recovery planner    | `C_pass`, `C_fail`          | `Images/DAG/7`–`8` |
| **4** | Coder prompt → SandboxExecutor; computation formatter cannot do from text         | `M`                         | `Images/DAG/9`     |
| **5** | One new skill (yaml + prompt only); one query; orchestrator unchanged             | `PROS`                      | `Images/DAG/10`    |


---

### Part 1 — Base queries (`hello`, `A`, `I`, `J`, `K`)

Pass the five base queries from this session **verbatim**, within the wall-clock bound on each card. Run in order from the **DAG Queries** tab (or `uv run python scripts/dag/run_query.py <id>`).


| Id        | Query (verbatim)                                                                                                                                                                              | Bound | Expected DAG                                             |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- | -------------------------------------------------------- |
| **hello** | Say hello.                                                                                                                                                                                    | 15s   | planner → formatter (2 nodes)                            |
| **A**     | Fetch [https://en.wikipedia.org/wiki/Claude_Shannon](https://en.wikipedia.org/wiki/Claude_Shannon) and tell me his birth date, death date, and three key contributions to information theory. | 180s  | planner → researcher → distiller → critic → formatter    |
| **I**     | Find the populations of London, Paris, Berlin and tell me which two are closest in size.                                                                                                      | 120s  | 3× researcher ∥ → coder → formatter (+ sandbox_executor) |
| **J**     | Read /nonexistent/path.txt and tell me what's in it.                                                                                                                                          | 30s   | planner → formatter (fail-fast, no tools)                |
| **K**     | For Lagos, Cairo, and Kinshasa, find current populations and growth rates and tell me which is growing fastest.                                                                               | 180s  | Same parallel shape as **I**; demo kill + **Resume**     |


<p align="center">
  <strong>hello</strong><br/>
  <img src="Images/DAG/1_a.png" width="49%" alt="hello chat"/>
  <img src="Images/DAG/1_b.png" width="49%" alt="hello live trace"/>
</p>

<p align="center">
  <strong>A — Shannon Wikipedia</strong><br/>
  <img src="Images/DAG/2_a.png" width="49%" alt="A working trace"/>
  <img src="Images/DAG/2_b.png" width="49%" alt="A researcher"/>
  <img src="Images/DAG/2_c.png" width="49%" alt="A graph"/>
  <img src="Images/DAG/2_d.png" width="49%" alt="A final answer"/>
</p>

<p align="center">
  <strong>I — parallel fan-out (canonical)</strong><br/>
  <img src="Images/DAG/3_a.png" width="49%" alt="I parallel wave"/>
  <img src="Images/DAG/3_b.png" width="49%" alt="I researchers"/>
  <img src="Images/DAG/3_c.png" width="49%" alt="I graph"/>
  <img src="Images/DAG/3_d.png" width="49%" alt="I answer"/>
</p>

<p align="center">
  <strong>J — graceful failure</strong><br/>
  <img src="Images/DAG/4_a.png" width="49%" alt="J fail-fast"/>
  <img src="Images/DAG/4_b.png" width="49%" alt="J formatter"/>
</p>

<p align="center">
  <strong>K — resumable execution</strong><br/>
  <img src="Images/DAG/5_a.png" width="32%" alt="K parallel start"/>
  <img src="Images/DAG/5_b.png" width="32%" alt="K mid-run"/>
  <img src="Images/DAG/5_c.png" width="32%" alt="K stop"/>
  <img src="Images/DAG/5_d.png" width="32%" alt="K resume"/>
  <img src="Images/DAG/5_e.png" width="32%" alt="K graph after resume"/>
  <img src="Images/DAG/5_f.png" width="32%" alt="K complete"/>
</p>

---

### Part 2 — Parallel fan-out (`P`)

Design one query with **≥3 independent sub-tasks** that the Planner emits as **concurrent nodes** in one wave. Verify the parallel layer's wall-clock is the **maximum of the branches**, not the sum.


| Id    | Query                                                                                                          | Verification                                                                                               |
| ----- | -------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| **P** | Find the current population of Tokyo, Mumbai, and São Paulo and tell me which city has the largest population. | `uv run python scripts/dag/analyze_session_timing.py dag_P_<timestamp> --json` → `parallel_confirmed=true` |

<p align="center">
  <img src="Images/DAG/6_a.png" width="32%" alt="P parallel researchers trace"/>
  <img src="Images/DAG/6_b.png" width="32%" alt="P timing"/>
  <img src="Images/DAG/6_c.png" width="32%" alt="P graph three researchers"/>
</p>

---

### Part 3 — Critic verdict (`C_pass`, `C_fail`)

Choose a property the Critic can verify with its tools (`validate_json_keys` on keys `author`, `title`, `year`). Run **both** queries: pass on **C_pass**; fail + recovery planner on **C_fail**.


| Id         | Query                                                                                                                 | Expected                                            |
| ---------- | --------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| **C_pass** | Validate JSON `{"author":"Ada Lovelace","title":"Notes","year":1843}` — critic verifies keys via `validate_json_keys` | Critic **pass** → formatter                         |
| **C_fail** | Same JSON but **missing `year`** — on fail, replan with year added                                                    | Critic **fail** → recovery planner → corrected JSON |


<p align="center">
  <strong>C_fail — recovery splice</strong><br/>
  <img src="Images/DAG/7_a.png" width="32%" alt="C_fail critic start"/>
  <img src="Images/DAG/7_b.png" width="32%" alt="C_fail recovery graph"/>
  <img src="Images/DAG/7_c.png" width="32%" alt="C_fail recovery trace"/>
</p>

<p align="center">
  <strong>C_pass — tool-verified pass</strong><br/>
  <img src="Images/DAG/8_a.png" width="32%" alt="C_pass query"/>
  <img src="Images/DAG/8_b.png" width="32%" alt="C_pass graph"/>
  <img src="Images/DAG/8_c.png" width="32%" alt="C_pass output"/>
</p>

---

### Part 4 — Coder + SandboxExecutor (`M`)

`prompts/coder.md` emits Python JSON `{code, summary}` for the SandboxExecutor. Query **M** requires exact integer arithmetic the Formatter cannot reliably do from text alone.


| Id    | Query                                                                                                      | Expected                                                          |
| ----- | ---------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| **M** | What is the exact integer value of `(17 * 23 - 4) ** 2 + 1000`? Use coder to compute; sandbox must verify. | planner → coder → sandbox_executor → formatter; answer **150769** |

<p align="center">
  <img src="Images/DAG/9_a.png" width="24%" alt="M coder graph"/>
  <img src="Images/DAG/9_b.png" width="24%" alt="M sandbox"/>
  <img src="Images/DAG/9_c.png" width="24%" alt="M stdout"/>
  <img src="Images/DAG/9_d.png" width="24%" alt="M final answer"/>
</p>

---

### Part 5 — New skill: prosody analyst (`PROS`)

Add **`prosody_analyst`** to `agent_config.yaml` + `prompts/prosody_analyst.md` (skill the catalogue did not cover). One UI query exercises it. **Orchestrator unchanged** — `calculator` also remains in the catalogue (no DAG Queries card; use Chat for arithmetic).

| Item       | Location                                                             |
| ---------- | -------------------------------------------------------------------- |
| New skill  | `prosody_analyst` + `count_syllables`                                |
| Demo query | **PROS** — three lines; Line **B** wins (A=11, B=17, C=13 syllables) |

<p align="center">
  <img src="Images/DAG/10_a.png" width="32%" alt="PROS graph"/>
  <img src="Images/DAG/10_b.png" width="32%" alt="PROS trace"/>
  <img src="Images/DAG/10_c.png" width="32%" alt="PROS answer"/>
</p>

## Architecture

```
USER_QUERY
    │
    ▼
┌─────────┐     extends graph      ┌──────────────────────────────┐
│ Planner │ ─────────────────────► │ researcher × N (parallel)    │
│ (skill) │                        │ distiller → critic → formatter│
└─────────┘                        │ coder → sandbox_executor      │
                                   │ calculator / prosody_analyst  │
                                   │ → formatter                 │
                                   └──────────────────────────────┘
```


| Component                     | Location                                                                                |
| ----------------------------- | --------------------------------------------------------------------------------------- |
| Graph + Executor + `DagAgent` | `cognitive_dag/flow.py`                                                                 |
| Graph viz (API / UI)          | `cognitive_dag/graph_viz.py`                                                            |
| Skill catalogue               | `agent_config.yaml` + `prompts/*.md`                                                    |
| Critic splice                 | Auto on `distiller` out-edges (`critic: true`)                                          |
| Recovery                      | `cognitive_dag/recovery.py` → `classify_failure`                                        |
| Persistence                   | `state/sessions/<sid>/` (`graph.json`, `nodes/*.json`, `query.txt`, `memory_hits.json`) |
| LLM                           | Gemini SDK default; optional `GATEWAY_V8_URL`                                           |


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
├── prompts/                 # planner, researcher, critic, coder, calculator, prosody_analyst, …
├── agent_config.yaml
├── agent_routing.yaml       # Optional gateway provider pins
├── app.py                   # FastAPI + /api/dag/*
├── templates/index.html     # Chat, DAG Queries (design blocks), Graph, Documents
├── corpus/dag/ASSIGNMENT.json   # Demo query corpus + design_queries metadata
├── scripts/dag/             # run_eval, run_query, analyze_session_timing
├── docs/ASSIGNMENT.md       # Detailed verification guide
├── docs/DEFERRALS.md
├── Images/DAG/              # Demo query screenshots (README)
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