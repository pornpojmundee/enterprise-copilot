# Nawa Copilot — Enterprise Support Multi-Agent Copilot

[![ci](https://github.com/pornpojmundee/enterprise-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/pornpojmundee/enterprise-copilot/actions/workflows/ci.yml)

An internal HR/IT assistant for a fictional 200-person Thai software company, **Nawa Tech**. Employees ask in Thai
(or English); the copilot answers from policy documents **with citations**, looks up their own leave and tickets
**within what they are allowed to see**, and opens or updates IT tickets **after they confirm** — with sign-in,
guardrails, an audit trail, a held-out + red-team evaluation, and a scale-to-zero deployment on Azure.

**Live demo:** https://ca-entcopilot-dev-swc.graywater-940e858f.swedencentral.azurecontainerapps.io
Sign in as `NT0082` (or any account listed on the page), password `nawa-demo-2026`. All data is fictional.
The app scales to zero when idle, so the first visit takes ~2–3 minutes to wake up.

| Sign-in | Prompt injection refused before any LLM call | Admin audit log |
|---|---|---|
| ![sign-in](docs/images/login.png) | ![guardrail](docs/images/guardrail.png) | ![audit](docs/images/audit.png) |

## What it does
| # | Who | Question | What happens |
|---|---|---|---|
| UC1 | Employee | "I take leave Friday 4 Dec and Monday is a substitute holiday — how many days, do I have enough?" | Policy (RAG) + own balance (SQL) + day count (code), in parallel, merged into one answer |
| UC2 | Employee | "I'm going to a 3-day seminar in Chiang Mai, what do I need to do?" | Steps across leave, travel approval and expense policies, each cited (e.g. `HR-003 §2`) |
| UC3 | New hire | "My notebook won't turn on, who do I tell? Open a ticket for me" | Policy answer + a ticket draft → **user confirms** → ticket created in NawaDesk |
| UC4 | Team lead | "How many open tickets does my team have, which are past SLA?" | Text-to-SQL; row-level security returns only that lead's org chart |
| UC5 | IT support | "Summarize IT-1042 and find similar past cases" | Ticket summary + trigram search over resolved tickets |
| UC6 | Admin | "What did people ask today, what was blocked, what did it cost?" | Append-only audit log page |

Security behaviour is specified the same way (SEC1–SEC5: salary questions, other teams' data, prompt injection,
ID numbers typed into chat, closing someone else's ticket) — see [docs/use-cases.md](docs/use-cases.md).

## Architecture
```mermaid
flowchart LR
    U[Browser] -->|HTTPS + JWT| API[FastAPI<br/>rate limit · daily budget]
    API --> G{{Guardrails<br/>PII masking · injection check}}
    G --> R[Router<br/>LangGraph]
    R --> K[Knowledge agent<br/>hybrid RAG]
    R --> D[Data agent<br/>Text-to-SQL]
    R --> C[Calendar tool<br/>pure code]
    R --> S[Summary agent]
    R --> A[Action agent<br/>MCP client]
    K & D & C & S & A --> M[Compose] --> O{{Output masking}} --> U
    A -. write? .-> H[/User confirms/] -.-> MCP[NawaDesk MCP server<br/>permission check]
    K --> PG[(Postgres<br/>pgvector · BM25 tokens)]
    D -->|read-only role + RLS| PG
    MCP --> PG
    API --> AU[(Audit log<br/>append-only)]
    R & K & D & M -.-> LLM[Azure OpenAI gpt-5-mini<br/>managed identity, no key]
```
Request walk-through and sequence diagram: [docs/architecture.md](docs/architecture.md) · 3-minute demo script: [docs/demo-video.md](docs/demo-video.md)

## Engineering decisions worth reading
- **The model decides wording, never access.** Who you are comes from a signed token; what you may see is enforced
  by Postgres row-level security (org chart) and document ACLs applied *before* retrieval; what you may change is
  checked by the MCP server on the real call. A fully prompt-injected model still cannot read or change more than
  the user could. → [docs/security.md](docs/security.md)
- **Hybrid retrieval for Thai.** bge-m3 vectors + BM25 over PyThaiNLP word tokens, fused with Reciprocal Rank Fusion,
  then a relevance gate: no evidence → "not found", no LLM call. → [docs/knowledge-agent.md](docs/knowledge-agent.md)
- **Text-to-SQL behind three walls**: an AST guard (single SELECT, view and function allowlists), a read-only role in
  a read-only transaction with a timeout, and RLS. One self-correction retry. → [docs/data-and-action-agents.md](docs/data-and-action-agents.md)
- **Arithmetic in code, not in the LLM.** Leave-day counting (weekends, substitute holidays, half days) is a function.
- **Human in the loop for every write**, implemented with LangGraph `interrupt()`; only the asker can confirm, once.
  → [docs/orchestrator.md](docs/orchestrator.md)
- **PII never leaves the box.** Thai national ID and card numbers are masked before the LLM, the audit log, Langfuse
  or a ticket sees them.
- **Measure, then trust.** Held-out sets written after tuning, every suite run 3× and reported as pass^k, and a
  red-team suite that *approves* every proposed write to prove the server refuses. → [docs/evaluation.md](docs/evaluation.md)
- **Cheap to run.** Scale-to-zero Container App, Postgres as a sidecar, image on GHCR, keyless Azure OpenAI, per-user
  rate limit and a daily LLM budget. Idle cost: 0. → [docs/deploy.md](docs/deploy.md)

## Results
Held-out sets, 3 runs each (gpt-5-mini, `reasoning_effort` low/minimal):

| | Routing (15) | Text-to-SQL (12) | Red-team (15) |
|---|---|---|---|
| Mean accuracy | 100% | 100% | 98% |
| pass^k (passed every run) | 100% | 100% | 93% |
| Median latency | 2.6 s | 5.4 s | 3.8 s |

The one red-team miss (a reply repeating a *real* ticket ID copied from a tool description example) was fixed by
using non-existent IDs in every prompt. Average cost ≈ **0.04 THB per question**. Full tables, method and caveats
(small sets, same author) in [docs/evaluation.md](docs/evaluation.md).

## Tech stack
| Area | Used |
|---|---|
| LLM | Azure OpenAI gpt-5-mini (v1 API, Entra ID auth), prompt shield as a second guardrail layer |
| Orchestration | LangGraph (parallel fan-out, `interrupt()` for confirmation), MCP Python SDK |
| Retrieval | bge-m3 (sentence-transformers), pgvector HNSW, rank-bm25 + PyThaiNLP, RRF |
| Data | PostgreSQL 16, row-level security, security-invoker views, sqlglot SQL guard |
| App | FastAPI, vanilla JS UI (strict CSP), Streamlit (internal demo), PyJWT, scrypt |
| Quality | pytest (135 tests), held-out + red-team eval suite, Langfuse tracing (optional) |
| Delivery | Docker, GitHub Actions → GHCR, Azure Container Apps (scale to zero, managed identity) |

## Run it locally
```bash
git clone https://github.com/pornpojmundee/enterprise-copilot && cd enterprise-copilot
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # Azure OpenAI endpoint + key: docs/setup-azure.md
docker compose up -d                                   # Postgres + pgvector
python scripts/bootstrap.py                            # schema, seed data, demo passwords, knowledge base
uvicorn copilot.api.app:app --port 8000                # http://localhost:8000  ·  API docs at /api/docs
python -m pytest -q                                    # tests (no LLM calls)
```
Or the production container: `docker compose --profile app up --build`. Windows one-shot setup:
`powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1`. Per-component commands (agents on the
command line, evals, Streamlit): [docs/development.md](docs/development.md).

## Repository layout
| Path | What |
|---|---|
| `src/copilot/agents/` | Knowledge, Data, Action, Summary agents |
| `src/copilot/orchestrator.py` | LangGraph router, parallel agents, compose, confirmation |
| `src/copilot/kb/` | Chunking, embeddings, hybrid retrieval |
| `src/copilot/data/` | SQL guard, read-only executor, schema description for the LLM |
| `src/copilot/guardrails.py`, `auth.py`, `audit.py` | PII masking + injection check, sign-in, audit log |
| `src/copilot/api/` | FastAPI app, rate limit / budget, web UI (`static/`) |
| `src/nawadesk_mcp/` | Ticket system exposed as an MCP server |
| `src/mock_hris/` | Mock HR system API (FastAPI) |
| `db/init/` | Schema, RLS policies, views, audit tables |
| `data/` | Policy documents, seed CSVs, eval sets (`eval/heldout/` = not used for tuning) |
| `scripts/` | Bootstrap, seed, evals, Azure deploy |
| `docs/` | Design notes per component, evaluation, deployment |

## Limitations and next steps
- Evaluation sets are small (42 held-out cases) and written by the builder; next: questions from real users, and
  regression evals in CI on every prompt change.
- PII detection covers ID and card numbers only; names and addresses in free text are not detected.
- The demo database resets on every cold start (no persistent disk) — production would use Azure Database for
  PostgreSQL and SSO (Entra ID) instead of passwords.
- Pending confirmations live in one process's memory; more than one replica would need a shared checkpointer.

## Project log
Built in 8 weekly steps — use cases → mock company → RAG → Text-to-SQL + MCP actions → orchestrator → security →
evaluation → deployment. Each step's design note is in `docs/`.

## License
MIT — see [LICENSE](LICENSE). Nawa Tech, its employees and documents are fictional.
