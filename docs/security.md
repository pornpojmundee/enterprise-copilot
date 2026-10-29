# Security layer (week 5)

Nawa Copilot handles HR and IT data, so the AI is treated as an **untrusted component**: everything that
matters (who you are, what you may see, what gets written) is decided in code or in the database,
never by the model.

```
 browser ──sign-in──> auth (scrypt, lockout) ──User──> Copilot.ask
                                                        │
                       guardrails.check_input  ◄────────┘   1. length cap
                         │  masked text only              2. injection pre-check (no LLM call)
                         ▼                                3. mask Thai ID / card numbers (SEC4)
                   LangGraph orchestrator ──> agents ──> Postgres RLS + read-only role (SEC1, SEC2)
                         │                         └──> NawaDesk MCP: permission check per tool (SEC5)
                         ▼
                 guardrails.mask_output ──> answer      audit.record ──> copilot_sec.audit_log (append-only)
```

## Sign-in — `src/copilot/auth.py`
- Passwords: `hashlib.scrypt` (n=2^14, r=8, p=1) with a random 16-byte salt; stored as `scrypt$n$r$p$salt$hash`.
- Sign in with employee ID or company e-mail. Resigned employees cannot sign in.
- 5 wrong passwords → account locked for 15 minutes.
- Unknown user, wrong password, locked and resigned all return the **same message**, and an unknown user
  still costs one hash check — the form does not reveal which employee IDs exist.
- Every attempt (success or failure, with the reason) goes to the audit log.
- The app signs you out after `SESSION_IDLE_MINUTES` (default 30) without activity.
- In a real company this would be SSO (Entra ID / OIDC); the rest of the system only needs a `User`, so
  swapping the sign-in does not touch the agents.

Demo accounts: the 7 personas in [demo-personas.md](demo-personas.md). `scripts/load_seed.py` gives them
`DEMO_PASSWORD` from `.env`. Other employees: `python scripts/set_password.py NT0123`.
`python -m copilot.chat --as ...` skips sign-in on purpose — it is a developer tool on your own machine.

## Guardrails — `src/copilot/guardrails.py`
| Check | How | Why in code |
|---|---|---|
| PII masking (SEC4) | Thai national ID in any format (`1-2345-67890-12-3`, spaced, plain; masked even with a bad checksum) and card numbers that pass Luhn → `[เลขบัตรประชาชน]` / `[เลขบัตร]` | Must happen *before* the text reaches the LLM, the audit log or a ticket. The user sees a notice. |
| Prompt injection (SEC3) | ~6 EN/TH patterns ("ignore previous instructions", "ลืมคำสั่ง…", "แสดง system prompt") | Free and instant; no tokens spent. Azure's prompt shield (`llm.ContentFiltered`) catches what the list misses. |
| Length cap | 2,000 characters | Cost and prompt-stuffing |
| Output masking | Same PII patterns on every answer and action result | Defence in depth if data ever contained an ID |

Phone numbers and work e-mails are **not** masked on purpose: people put a call-back number in IT tickets,
and colleague e-mails are directory data.

Known limits: pattern lists are easy to rephrase around (that is what layer 2 and RLS are for); PII other
than ID/card numbers (names in free text, addresses) is not detected.

## Audit log — `db/init/005_security.sql`, `src/copilot/audit.py`
One row per `login`, `login_failed`, `logout`, `ask`, `confirm`: who, role, masked question, agents, sources,
the SQL the Data agent ran, the write tool and its arguments, guardrail hit, PII types masked (never the value),
LLM calls, cost, latency.
- **Append-only**: triggers reject `UPDATE`, `DELETE` and `TRUNCATE`.
- Not granted to `copilot_reader`, so generated SQL cannot read it (or the password hashes).
- Writing is best-effort: if the DB is briefly unavailable the chat still answers and the error is printed.
- Admins (`NT0016` Wut) see it in the app: sidebar → **Audit log** (today's questions, blocks, PII masked, cost).

## Confirmations
`Copilot.confirm(turn, approved, user)` only works for the user who asked and only once — a pending write
cannot be approved by someone else or replayed. The MCP server re-checks permissions on the actual call.

## Tests
`tests/test_guardrails.py` (offline), `tests/test_auth_audit.py` (needs Postgres; adds a few login rows to the
audit log — it is append-only by design), new cases in `tests/test_orchestrator.py` and `tests/test_streamlit_app.py`.
