"""Contract validation checks. No MongoDB needed — every case fails before the DB."""
from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app, raise_server_exceptions=False)


def test_health_matches_db_state():
    r = c.get("/health")
    if r.status_code == 200:
        assert r.json() == {"status": "ok"}
    else:
        assert r.status_code == 503
        assert "detail" in r.json()


def test_employee_validation():
    bad_code = {"emp_code": "X", "name": "A", "email": "a@b.co", "department": "E", "joined_on": "2026-01-05"}
    assert c.post("/employees", json=bad_code).status_code == 422
    good = dict(bad_code, emp_code="EMP0007")
    good["shift_start"] = good["shift_end"] = "09:30"
    assert c.post("/employees", json=good).status_code == 422
    assert c.get("/employees", params={"page_size": 101}).status_code == 422


def test_punch_validation():
    assert c.post("/attendance/punch-in", json={"emp_code": "EMP0001", "punched_at": 1750000000}).status_code == 422
    assert c.post("/attendance/punch-in", json={"emp_code": "EMP0001", "punched_at": 1783312500000.5}).status_code == 422
    assert c.post("/attendance/punch-in", json={"emp_code": "EMP0001", "status": "ABSENT"}).status_code == 422
    assert c.post("/attendance/punch-out", json={"emp_code": "EMP0001", "punched_at": 1}).status_code == 422


def test_list_and_analytics_validation():
    assert c.get("/attendance", params={"date_from": "2026-07-08", "date_to": "2026-07-07"}).status_code == 422
    assert c.get("/attendance", params={"status": "NOPE"}).status_code == 422
    assert c.get("/analytics/employees/EMP0001/monthly", params={"month": "2026-13"}).status_code == 422
    assert c.get("/analytics/departments/summary", params={"month": "xx"}).status_code == 422
    assert c.get("/analytics/leaderboard/late", params={"month": "2026-07", "limit": 51}).status_code == 422
    assert c.get("/analytics/departments/Eng/trend", params={"from": "2026-07-08", "to": "2026-07-07"}).status_code == 422
    assert c.patch("/attendance/EMP0001/2026-07-07", json={"reason": "bad", "regularized_by": "hr"}).status_code == 422
    assert c.get("/admin/explain/nope").status_code == 422
    assert c.get("/admin/explain/employee_monthly").status_code == 422
