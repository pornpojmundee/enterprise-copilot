# Enterprise Support Multi-Agent Copilot

A multi-agent AI copilot for internal HR/IT support at a fictional company (Nawa Tech). It answers policy questions with citations, queries business data with role-based access, and takes actions such as opening tickets — with guardrails, evaluation and observability built in.

> Status: **Week 0 — project setup**

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
```

## Project layout
| Path | What |
|---|---|
| `src/copilot/` | Application code |
| `data/documents/` | Mock HR/IT policy documents (week 1) |
| `data/seed/` | Mock employees, teams, tickets (week 1) |
| `db/init/` | SQL run on first DB start |
| `docs/` | Use cases, setup guide, architecture and Responsible AI docs |
| `scripts/` | Setup and utility scripts |
| `tests/` | Unit tests and eval suites |

## Roadmap
- [x] Week 0 — repo, Docker DB, Azure OpenAI, use cases
- [ ] Week 1 — mock company data + mock HRIS API
- [ ] Week 2 — Knowledge agent (hybrid RAG + citations)
- [ ] Week 3 — Data agent (Text-to-SQL) + Action agent (MCP)
- [ ] Week 4 — Orchestrator (LangGraph) + Summary agent
- [ ] Week 5 — Auth, RBAC, row-level security, guardrails
- [ ] Week 6 — Evaluation + red-team + Langfuse
- [ ] Week 7 — FastAPI, UI, Docker, CI/CD, Azure deploy
- [ ] Week 8 — Docs and demo video

See [docs/use-cases.md](docs/use-cases.md) for the demo scenarios.
