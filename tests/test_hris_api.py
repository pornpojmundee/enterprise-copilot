"""Integration tests for the mock HRIS. Need Postgres running with seed data loaded:

    docker compose up -d && python scripts/load_seed.py && pytest
"""
import psycopg
import pytest
from fastapi.testclient import TestClient

from copilot.config import postgres_dsn

try:
    with psycopg.connect(postgres_dsn(), connect_timeout=3) as c:
        c.execute("SELECT 1 FROM hris.employees LIMIT 1")
except Exception:  # noqa: BLE001
    pytest.skip("Postgres with seed data not available", allow_module_level=True)

from mock_hris.auth import DEFAULT_DEV_KEY  # noqa: E402
from mock_hris.main import app  # noqa: E402

client = TestClient(app)

# Personas from docs/demo-personas.md
PLOY, NEW_HIRE, DATA_LEAD, HR = "NT0082", "NT0197", "NT0031", "NT0061"


def h(emp: str, key: str = DEFAULT_DEV_KEY) -> dict:
    return {"X-API-Key": key, "X-Acting-Employee-Id": emp}


def test_requires_api_key():
    assert client.get("/me", headers=h(PLOY, "wrong")).status_code == 401
    assert client.get("/me").status_code == 422  # headers missing


def test_me_has_no_salary():
    body = client.get("/me", headers=h(PLOY)).json()
    assert body["employee_id"] == PLOY
    assert not any("salary" in k for k in body)


def test_uc1_balance_and_working_days():
    bal = client.get(f"/employees/{PLOY}/leave-balances?year=2026", headers=h(PLOY)).json()
    vac = next(b for b in bal["balances"] if b["leave_type"] == "VAC")
    assert vac["remaining"] == 1.5
    wd = client.get("/calendar/working-days?start=2026-12-04&end=2026-12-07", headers=h(PLOY)).json()
    assert wd["leave_days_deducted"] == 1
    assert wd["days"][-1]["type"] == "holiday"


def test_employee_cannot_see_others():
    assert client.get(f"/employees/{DATA_LEAD}", headers=h(PLOY)).status_code == 404
    assert client.get(f"/employees/{PLOY}/leave-balances", headers=h(NEW_HIRE)).status_code == 404


def test_manager_and_hr_can_see_report():
    assert client.get(f"/employees/{PLOY}/leave-balances", headers=h(DATA_LEAD)).status_code == 200
    assert client.get(f"/employees/{PLOY}/leave-balances", headers=h(HR)).status_code == 200


def test_team_members_access():
    assert client.get("/teams/DATA-DE/members", headers=h(DATA_LEAD)).status_code == 200
    assert client.get("/teams/SALES-SMB/members", headers=h(DATA_LEAD)).status_code == 404  # SEC2-style
    assert client.get("/teams/DATA-DE/members", headers=h(PLOY)).status_code == 404


def test_probation_cannot_take_vac():
    r = client.post("/leave-requests", headers=h(NEW_HIRE),
                    json={"leave_type": "VAC", "start_date": "2026-11-20", "end_date": "2026-11-20", "dry_run": True})
    assert r.status_code == 200
    assert "PROBATION_NO_VAC" in [v["code"] for v in r.json()["violations"]]


def test_insufficient_balance():
    r = client.post("/leave-requests", headers=h(PLOY),
                    json={"leave_type": "VAC", "start_date": "2026-12-14", "end_date": "2026-12-15", "dry_run": True})
    assert [v["code"] for v in r.json()["violations"]] == ["INSUFFICIENT_BALANCE"]


def test_submit_then_cancel_restores_balance():
    payload = {"leave_type": "VAC", "start_date": "2026-12-04", "end_date": "2026-12-07", "reason": "test"}
    r = client.post("/leave-requests", headers=h(PLOY), json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending" and body["working_days"] == 1 and body["balance_after"] == 0.5
    # second identical request overlaps
    dup = client.post("/leave-requests", headers=h(PLOY), json=payload)
    assert dup.status_code == 422
    # someone else can't cancel it
    assert client.post(f"/leave-requests/{body['request_id']}/cancel", headers=h(DATA_LEAD)).status_code == 404
    c = client.post(f"/leave-requests/{body['request_id']}/cancel", headers=h(PLOY))
    assert c.status_code == 200
    bal = client.get(f"/employees/{PLOY}/leave-balances?year=2026", headers=h(PLOY)).json()
    assert next(b for b in bal["balances"] if b["leave_type"] == "VAC")["remaining"] == 1.5


def test_holidays_listed():
    hol = client.get("/holidays?year=2026", headers=h(PLOY)).json()["holidays"]
    assert len(hol) == 19
    assert sum(x["is_substitute"] for x in hol) == 2
