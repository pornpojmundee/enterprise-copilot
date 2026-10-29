"""Nawa Copilot HTTP API + web UI (week 7).

    uvicorn copilot.api.app:app --port 8000          # then open http://localhost:8000

Endpoints (JSON; all but login/health need `Authorization: Bearer <token>`):
  POST /api/login                      {login, password} -> {token, user}
  POST /api/logout
  GET  /api/me
  POST /api/chat                       {question, history?, session_id?} -> answer, agents, sources, pending...
  POST /api/chat/{thread_id}/confirm   {approved} -> outcome       (only the asker, only once)
  GET  /api/admin/audit                admin only
  GET  /healthz  (process up)   GET /readyz  (database reachable)
The web UI (static/) is served at /.

Identity comes only from the signed token (HS256, API_SECRET_KEY); the chat text can never change
who you are. Guards for a public URL: per-user rate limit and a daily LLM budget (limits.py).
"""
from __future__ import annotations

import os
import secrets
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Literal

import jwt
import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from copilot import audit, auth
from copilot.config import postgres_dsn
from copilot.orchestrator import Copilot, Turn
from copilot.users import User, get_user

from .limits import DailyBudget, RateLimiter

STATIC = Path(__file__).parent / "static"
TOKEN_MINUTES = int(os.getenv("SESSION_IDLE_MINUTES", "30"))
PENDING_TTL_S = 15 * 60
DEMO_MODE = os.getenv("DEMO_MODE", "1") == "1"


def _secret() -> str:
    key = os.getenv("API_SECRET_KEY")
    if not key:  # dev convenience: random per process (tokens die on restart). Set it in production.
        key = os.environ.setdefault("API_SECRET_KEY", secrets.token_urlsafe(32))
    return key


class State:
    """Process-wide objects. One replica keeps pending confirmations in memory (LangGraph InMemorySaver)."""
    copilot: Copilot | None = None
    pending: dict[str, tuple[float, Turn]] = {}
    limiter = RateLimiter()
    budget = DailyBudget()
    lock = threading.Lock()


def get_copilot() -> Copilot:
    with State.lock:
        if State.copilot is None:
            State.copilot = Copilot()
        return State.copilot


def _warm_up() -> None:
    """Load the embedding model before the first question (cold starts happen on scale-from-zero)."""
    if os.getenv("WARM_UP", "1") != "1":
        return
    try:
        from copilot import orchestrator
        orchestrator._knowledge()
        print("[api] knowledge agent warmed up", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[api] warm-up skipped: {e}", flush=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    _secret()
    threading.Thread(target=_warm_up, daemon=True).start()
    yield


app = FastAPI(title="Nawa Copilot API", version="1.0", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.update({
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store" if request.url.path.startswith("/api/") else "public, max-age=300",
    })
    if not request.url.path.startswith("/api/docs"):
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; img-src 'self' data:; frame-ancestors 'none'")
    return resp


# ---------------- auth ----------------
bearer = HTTPBearer(auto_error=False)


def issue_token(user: User) -> str:
    now = int(time.time())
    return jwt.encode({"sub": user.employee_id, "role": user.app_role, "iat": now,
                       "exp": now + TOKEN_MINUTES * 60}, _secret(), algorithm="HS256")


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in required")
    try:
        claims = jwt.decode(creds.credentials, _secret(), algorithms=["HS256"])
        return get_user(claims["sub"])       # re-read: a resigned employee loses access immediately
    except (jwt.PyJWTError, LookupError, KeyError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired — please sign in again") from None


class LoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=200)


def _user_out(u: User) -> dict:
    return {"employee_id": u.employee_id, "name": u.name, "app_role": u.app_role, "team_id": u.team_id}


@app.post("/api/login")
def login(body: LoginIn):
    try:
        user = auth.authenticate(body.login, body.password)
    except auth.AuthError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from None
    return {"token": issue_token(user), "expires_in": TOKEN_MINUTES * 60, "user": _user_out(user)}


@app.post("/api/logout")
def logout(user: User = Depends(current_user)):
    auth.logout(user)
    return {"ok": True}


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return {"user": _user_out(user), "token": issue_token(user)}   # sliding session: fresh token


@app.get("/api/demo-accounts")
def demo_accounts():
    if not DEMO_MODE:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    with psycopg.connect(postgres_dsn()) as c:
        rows = c.execute("SELECT employee_id, nickname, position, app_role FROM hris.employees "
                         "WHERE employee_id = ANY(%s) ORDER BY employee_id", (list(auth.DEMO_ACCOUNTS),)).fetchall()
    return [{"employee_id": r[0], "name": r[1], "position": r[2], "app_role": r[3]} for r in rows]


# ---------------- chat ----------------
class Msg(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)   # guardrails cap at 2000 and explain why
    history: list[Msg] = Field(default_factory=list, max_length=20)
    session_id: str | None = Field(default=None, max_length=64)


def _turn_out(t: Turn) -> dict:
    d = asdict(t)
    d["cost_usd"] = round(t.cost_usd, 6)
    d["llm_calls"] = len(t.usages)
    d.pop("usages")
    if t.pending:
        d["pending"] = {"tool": t.pending.get("tool"), "preview": t.pending.get("preview")}  # not raw arguments
    return d


@app.post("/api/chat")
def chat(body: ChatIn, user: User = Depends(current_user)):
    if not State.limiter.allow(user.employee_id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "ถามถี่เกินไป รอสักครู่แล้วลองใหม่ครับ")
    if State.budget.exhausted():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "งบค่า AI ของวันนี้สำหรับเดโมหมดแล้ว ลองใหม่พรุ่งนี้ครับ")
    turn = get_copilot().ask(body.question, user, [m.model_dump() for m in body.history[-8:]],
                             session_id=body.session_id)
    if turn.pending:
        now = time.monotonic()
        with State.lock:
            for k in [k for k, (ts, _) in State.pending.items() if now - ts > PENDING_TTL_S]:
                del State.pending[k]
            State.pending[turn.thread_id] = (now, turn)
    return _turn_out(turn)


class ConfirmIn(BaseModel):
    approved: bool


@app.post("/api/chat/{thread_id}/confirm")
def confirm(thread_id: str, body: ConfirmIn, user: User = Depends(current_user)):
    with State.lock:
        entry = State.pending.get(thread_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบรายการที่รอยืนยัน (อาจหมดเวลาแล้ว)")
    try:
        done = get_copilot().confirm(entry[1], body.approved, user)
    except PermissionError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบรายการที่รอยืนยัน") from None  # same as missing
    with State.lock:
        State.pending.pop(thread_id, None)
    return {"thread_id": thread_id, "approved": body.approved, "outcome": done.action_outcome}


# ---------------- admin ----------------
@app.get("/api/admin/audit")
def admin_audit(limit: int = 100, user: User = Depends(current_user)):
    if user.app_role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    rows = audit.recent(max(1, min(limit, 500)))
    summary = audit.summary_today()
    summary["cost_usd"] = float(summary["cost_usd"])
    summary["budget_usd"] = State.budget.limit
    return {"summary": summary, "rows": rows}


# ---------------- health ----------------
@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    try:
        with psycopg.connect(postgres_dsn(), connect_timeout=3) as c:
            c.execute("SELECT 1")
    except Exception:  # noqa: BLE001
        return JSONResponse({"status": "database unavailable"}, status_code=503)
    return {"status": "ready"}


# ---------------- web UI ----------------
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
