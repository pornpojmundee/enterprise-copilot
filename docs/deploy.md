# Running and deploying (week 7)

## Three ways to run
| | Command | For |
|---|---|---|
| Dev | `uvicorn copilot.api.app:app --reload --port 8000` | coding (uses your `.env`, local Postgres on 5433) |
| One container, locally | `docker compose --profile app up --build` → http://localhost:8000 | checking the production image before deploying |
| Azure | `bash scripts/azure/deploy_containerapp.sh` (in Cloud Shell) | the public demo |

Streamlit (`streamlit run app/streamlit_app.py`) stays as the quick internal demo; the FastAPI app + web UI
(`src/copilot/api/`) is the production front end.

## The API
Interactive docs at `/api/docs`. Sign in with `POST /api/login`, then send `Authorization: Bearer <token>`.
- Identity only from the signed token (HS256, `API_SECRET_KEY`); tokens expire after `SESSION_IDLE_MINUTES`
  and `/api/me` hands out a fresh one (sliding session). A resigned employee is rejected on the next request.
- Pending actions: only the asker can confirm, once; raw tool arguments are never sent to the browser.
- Public-demo guards: `RATE_LIMIT_PER_MIN` per user, `DAILY_LLM_BUDGET_USD` for everyone (counted from the
  audit log); request size limits; security headers with a strict Content-Security-Policy (no inline script —
  the UI is three static files and inserts server text with `textContent` only).

## Image
`Dockerfile`: Python 3.13 slim, CPU-only PyTorch, bge-m3 baked in (no download at start), runs as a non-root
user. On start `scripts/bootstrap.py` creates schema, seed data, demo passwords and the knowledge-base index,
then uvicorn starts. GitHub Actions (`.github/workflows/ci.yml`) runs the tests against a real pgvector
Postgres on every push and, on `main`, pushes `ghcr.io/pornpojmundee/enterprise-copilot:latest`.

## Azure: Container Apps, scale to zero
```
            Internet ──HTTPS──> Container Apps ingress
                                     │ (0 replicas when idle → first request wakes it, ~2-3 min)
                    ┌────────────────┴───────────────────┐
                    │ replica                            │
                    │  app  (2 vCPU / 4 GiB)  ──localhost──>  db: pgvector/pgvector:pg16 (0.5 vCPU / 1 GiB)
                    └────────────────┬───────────────────┘
                                     │ managed identity (no API key)
                                     ▼
                     Azure OpenAI oai-entcopilot-dev-swc (gpt-5-mini)
```
Decisions:
- **Scale to zero** — idle costs nothing; active time is covered by the Container Apps monthly free grant for a
  demo's traffic. The price is a slow first request.
- **Postgres as a sidecar without a disk** instead of Azure Database for PostgreSQL (~500+ THB/month even idle).
  The demo data is regenerated on every cold start, which also resets anything visitors changed. The audit log
  does not survive a restart — fine for a demo, not for production (use Flexible Server there).
- **Keyless Azure OpenAI** — the app's system-assigned identity has the *Cognitive Services OpenAI User* role;
  `LLM_AUTH=entra` makes the OpenAI client fetch Entra tokens. No key in the image, env or repo.
- **No Log Analytics workspace** (`--logs-destination none`) — avoids ingestion charges; use `az containerapp logs show`.
- **Image from GHCR** (free for public packages) instead of Azure Container Registry (~170 THB/month).

### Deploy
1. GitHub → your profile → **Packages** → `enterprise-copilot` → *Package settings* → **Change visibility → Public**
   (once; the CI must have pushed the image first).
2. portal.azure.com → Cloud Shell (Bash):
   ```
   git clone https://github.com/pornpojmundee/enterprise-copilot && cd enterprise-copilot
   bash scripts/azure/deploy_containerapp.sh
   ```
3. Open the printed URL. First load after idle ≈ 2-3 minutes.

Update after a new image: run the script again. Logs: `az containerapp logs show -n ca-entcopilot-dev-swc -g rg-entcopilot-dev-swc --container app --follow`.

### Remove (stops all Container Apps charges)
```
az containerapp delete -n ca-entcopilot-dev-swc -g rg-entcopilot-dev-swc -y
az containerapp env delete -n cae-entcopilot-dev-swc -g rg-entcopilot-dev-swc -y
```
