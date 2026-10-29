# Development guide

Per-component commands, in the order the project was built. For the overview see the [README](../README.md).

## Commands by component
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

# Week 7: production API + web UI
uvicorn copilot.api.app:app --port 8000                       # http://localhost:8000  (API docs: /api/docs)
docker compose --profile app up --build                       # the same, as the production container
```

**Windows shortcut:** `powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1` runs all of the above (except Azure) and saves `setup-log.txt`.
If PostgreSQL is also installed on Windows it already owns port 5432 — set `POSTGRES_PORT=5433` in `.env` (docker-compose and the app both read it).

## Mock company: Nawa Tech
| What | Where |
|---|---|
| ~200 employees, 7 departments, 14 teams, leave balances/requests, 540 IT/HR tickets | `data/seed/*.csv` (regenerate: `python scripts/generate_seed.py`, deterministic) |
| 7 policy documents in Thai (leave, holidays, travel, compensation*, IT SLA, security, onboarding) | `data/documents/` — YAML front matter carries `access_roles` for RBAC |
| Two "systems of record" | Postgres schemas `hris` (NawaHR) and `itsm` (NawaDesk) — see `db/init/002_schema.sql` |
| Demo users for each use case | [docs/demo-personas.md](demo-personas.md) |

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

