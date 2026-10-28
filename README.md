# Enterprise Support Multi-Agent Copilot

A multi-agent AI copilot for internal HR/IT support at a fictional company (Nawa Tech). It answers policy questions with citations, queries business data with role-based access, and takes actions such as opening tickets — with guardrails, evaluation and observability built in.

> Status: **Week 2 — Knowledge agent (hybrid RAG with citations and permission filtering)**

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
| `src/copilot/agents/` | Agents (knowledge so far) |
| `src/mock_hris/` | NawaHR mock API (FastAPI) |
| `data/eval/` | Golden question sets |
| `tests/` | Unit tests and eval suites |

## Roadmap
- [x] Week 0 — repo, Docker DB, Azure OpenAI, use cases
- [x] Week 1 — mock company data + mock HRIS API
- [x] Week 2 — Knowledge agent (hybrid RAG + citations)
- [ ] Week 3 — Data agent (Text-to-SQL) + Action agent (MCP)
- [ ] Week 4 — Orchestrator (LangGraph) + Summary agent
- [ ] Week 5 — Auth, RBAC, row-level security, guardrails
- [ ] Week 6 — Evaluation + red-team + Langfuse
- [ ] Week 7 — FastAPI, UI, Docker, CI/CD, Azure deploy
- [ ] Week 8 — Docs and demo video

See [docs/use-cases.md](docs/use-cases.md) for the demo scenarios.
