# Enterprise Support Multi-Agent Copilot

A multi-agent AI copilot for internal HR/IT support at a fictional company (Nawa Tech). It answers policy questions with citations, queries business data with role-based access, and takes actions such as opening tickets — with guardrails, evaluation and observability built in.

> Status: **Week 6 — held-out + red-team evaluation with repeated runs, Langfuse tracing**

## Architecture (target)
```
User (Web / Teams) → FastAPI + Auth → Input guardrails
   → Orchestrator (LangGraph)
       ├─ Knowledge agent  (hybrid RAG over policy docs, pgvector + BM25)
       ├─ Data agent       (Text-to-SQL with row-level security)
       ├─ Action agent     (MCP tools: create ticket, etc.)
       └─ Summary agent
   → Output guardrails + citations → User
   Traces → Langfuse   ·   Eval → golden set + red-team tests
```

## Quick start
```bash
git clone <this repo> && cd enterprise-copilot
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then fill in Azure values (see docs/setup-azure.md)
docker compose up -d        # Postgres + pgvector
python scripts/check_setup.py

# Week 1: mock company data + HRIS API
python scripts/load_seed.py                                   # load data/seed/*.csv into Postgres
uvicorn mock_hris.main:app --app-dir src --port 8001          # API docs: http://localhost:8001/docs
pytest

# Week 2: Knowledge agent
python -m copilot.kb.index                                    # chunk + embed policy docs (first run downloads bge-m3)
python scripts/eval_retrieval.py                              # retrieval quality: BM25 vs vector vs hybrid (free)
python -m copilot.agents.knowledge "ลาป่วยกี่วันต้องมีใบรับรองแพทย์" --as NT0082 --show-context
python -m copilot.usage                                       # LLM tokens and cost so far

# Week 3: Data agent + Action agent
python -m copilot.agents.data "ทีมฉันมี ticket ค้างกี่ใบ อันไหนเกิน SLA" --as NT0031 --show-sql
python -m copilot.agents.action "notebook เปิดไม่ติด ช่วยเปิดเรื่องให้หน่อย" --as NT0197
python scripts/eval_text_to_sql.py                            # execution accuracy (~1 THB)

# Week 4: one chat for everything (routes to the right agents)
python -m copilot.chat --as NT0082 --trace
python scripts/eval_routing.py                                # routing accuracy (~0.2 THB)

# Week 5: sign-in + audit log + guardrails
python scripts/load_seed.py                                   # also creates the audit tables + demo passwords
streamlit run app/streamlit_app.py                            # sign in, e.g. NT0082 / DEMO_PASSWORD from .env
python scripts/set_password.py NT0123                         # give another employee a password

# Week 6: evaluation + tracing
python scripts/eval_suite.py --write                          # held-out routing/SQL + red-team, 3 runs (~6 THB)
python scripts/eval_suite.py --split dev --suite routing,sql  # the sets the system was tuned on
```

**Windows shortcut:** `powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1` runs all of the above (except Azure) and saves `setup-log.txt`.
If PostgreSQL is also installed on Windows it already owns port 5432 — set `POSTGRES_PORT=5433` in `.env` (docker-compose and the app both read it).

## Mock company: Nawa Tech
| What | Where |
|---|---|
| ~200 employees, 7 departments, 14 teams, leave balances/requests, 540 IT/HR tickets | `data/seed/*.csv` (regenerate: `python scripts/generate_seed.py`, deterministic) |
| 7 policy documents in Thai (leave, holidays, travel, compensation*, IT SLA, security, onboarding) | `data/documents/` — YAML front matter carries `access_roles` for RBAC |
| Two "systems of record" | Postgres schemas `hris` (NawaHR) and `itsm` (NawaDesk) — see `db/init/002_schema.sql` |
| Demo users for each use case | [docs/demo-personas.md](docs/demo-personas.md) |

\* `HR-004` is restricted to `hr` / `executive` — used by security test SEC1.

### NawaHR mock API
Every call sends `X-API-Key` (the copilot's service key) **and** `X-Acting-Employee-Id` (the user it acts for).
The HRIS enforces access itself — self, own reporting line, or HR — so a prompt-injected agent still can't read other people's data.

| Endpoint | Purpose |
|---|---|
| `GET /me`, `GET /employees/{id}` | Profile (never salary) |
| `GET /employees/{id}/leave-balances` | Entitled / carried over / used / pending / remaining |
| `GET /employees/{id}/leave-requests` | Leave history |
| `GET /calendar/working-days?start&end` | Days deducted + per-day reason (weekend / holiday) — UC1 |
| `GET /holidays?year` | Company holidays (HR-002) |
| `POST /leave-requests` (`dry_run` supported) | Validate against policy, then submit — returns violations with policy references |
| `POST /leave-requests/{id}/cancel` | Cancel own request before it starts |
| `GET /teams/{id}/members` | Roster + leave remaining — team lead / dept head / HR only |

## Knowledge agent (week 2)
```
question + user role
   → permission filter (access_roles ∩ user roles)          ← restricted docs never reach the LLM
   → vector search (bge-m3, pgvector HNSW)  ┐
   → BM25 (PyThaiNLP word tokens)           ┴→ Reciprocal Rank Fusion → top 5 sections
   → relevance gate (no evidence → answer "not found", no LLM call)
   → gpt-5-mini with grounded prompt → answer with [n] → mapped to "HR-001 §3.2 ลาป่วย"
   → tokens + cost logged to logs/llm_usage.jsonl
```
Design notes and evaluation: [docs/knowledge-agent.md](docs/knowledge-agent.md)

## Data agent + Action agent (week 3)
```
Data:   question → LLM writes SQL over copilot_data views → SQL guard (SELECT only, view + function allowlist)
        → run as the user: read-only role + READ ONLY tx + 5 s timeout + Postgres row-level security
        → LLM explains the rows
Action: request → NawaDesk MCP server (started as the user) → tools discovered via MCP
        → read tools run → write tools return a preview → user confirms → server re-checks permissions
```
Details: [docs/data-and-action-agents.md](docs/data-and-action-agents.md)

## Orchestrator (week 4)
```
                        ┌─> knowledge ─┐
    question ─> router ─┼─> data ──────┤
     (+history)         ├─> calendar ──┼─> compose ─> pending write? ─> confirm (LangGraph interrupt) ─> END
                        ├─> summary ───┤
                        └─> action ────┘
```
One small router call picks the agents and rewrites a sub-question for each; agents run in parallel;
one agent → answer passed through (no extra call), several → one compose call. Leave-day arithmetic is done
in code (`copilot/tools/calendar.py`), not by the LLM. Details: [docs/orchestrator.md](docs/orchestrator.md)

## Security layer (week 5)
| Layer | What it does | Security test |
|---|---|---|
| Sign-in (`copilot/auth.py`) | scrypt-hashed passwords, 5 failures → 15 min lock, same error for unknown user / wrong password | — |
| Guardrails (`copilot/guardrails.py`) | masks Thai national ID / card numbers **before** the LLM, the log or a ticket sees them; refuses obvious prompt injection without an LLM call; Azure prompt shield is layer 2 | SEC3, SEC4 |
| Identity | agents only get the signed-in user; only the asker can confirm their pending action | SEC5 |
| Row-level security | Postgres RLS by org chart; Data agent runs as a read-only role | SEC1, SEC2 |
| Audit log | append-only table (`copilot_sec.audit_log`): every login, question, SQL, tool call and confirmation; admin view in the app | UC6 |

Details: [docs/security.md](docs/security.md)

## Evaluation and tracing (week 6)
Held-out sets written after tuning, a 15-case red-team set with deterministic checks (no LLM judge), and every
suite run 3× — reported as mean, min–max and **pass^k** (passed in every run). Optional Langfuse tracing: one trace
per turn, one generation per LLM call, with tokens and cost. Details: [docs/evaluation.md](docs/evaluation.md)

## Project layout
| Path | What |
|---|---|
| `src/copilot/` | Application code |
| `data/documents/` | Mock HR/IT policy documents (week 1) |
| `data/seed/` | Mock employees, teams, tickets (week 1) |
| `db/init/` | SQL run on first DB start |
| `docs/` | Use cases, setup guide, architecture and Responsible AI docs |
| `scripts/` | Setup and utility scripts |
| `src/copilot/kb/` | Knowledge base: chunking, embeddings, hybrid retrieval |
| `src/copilot/agents/` | Knowledge, Data, Action and Summary agents |
| `src/copilot/orchestrator.py`, `chat.py` | LangGraph router/orchestrator and terminal chat |
| `app/streamlit_app.py` | Demo UI (Streamlit) |
| `src/copilot/data/` | SQL guard, read-only executor, semantic layer description |
| `src/nawadesk_mcp/` | NawaDesk ticket system as an MCP server |
| `src/mock_hris/` | NawaHR mock API (FastAPI) |
| `data/eval/` | Golden question sets |
| `tests/` | Unit tests and eval suites |

## Roadmap
- [x] Week 0 — repo, Docker DB, Azure OpenAI, use cases
- [x] Week 1 — mock company data + mock HRIS API
- [x] Week 2 — Knowledge agent (hybrid RAG + citations)
- [x] Week 3 — Data agent (Text-to-SQL) + Action agent (MCP)
- [x] Week 4 — Orchestrator (LangGraph) + Summary agent
- [x] Week 5 — Sign-in, audit log, guardrails (PII masking, injection pre-check)
- [x] Week 6 — Held-out + red-team evaluation (repeated runs), Langfuse tracing
- [ ] Week 7 — FastAPI, UI, Docker, CI/CD, Azure deploy
- [ ] Week 8 — Docs and demo video

See [docs/use-cases.md](docs/use-cases.md) for the demo scenarios.
