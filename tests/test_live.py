"""Live-database checks: races, ties, zero-log headcount. Skip cleanly without MongoDB."""
import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app, ensure_indexes

try:
    ensure_indexes()
    from pymongo import MongoClient

    MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=2000).admin.command("ping")
    LIVE = True
except Exception:
    LIVE = False

needs_db = pytest.mark.skipif(not LIVE, reason="needs live MongoDB")
c = TestClient(app, raise_server_exceptions=False)

_TEST_EMPS = ["EMP9101", "EMP9201", "EMP9202", "EMP9203", "EMP9301"]


def _reset():
    from pymongo import MongoClient

    db = MongoClient("mongodb://localhost:27017")["attendance_db"]
    db.attendance_logs.delete_many({"emp_code": {"$in": _TEST_EMPS}})
    db.employees.delete_many({"emp_code": {"$in": _TEST_EMPS}})


def _ms(y, mo, d, h, mi):
    return int(datetime.datetime(y, mo, d, h, mi, tzinfo=datetime.timezone.utc).timestamp() * 1000)


@needs_db
def test_parallel_punch_in_race():
    from concurrent.futures import ThreadPoolExecutor

    _reset()
    c.post("/employees", json={"emp_code": "EMP9101", "name": "R", "email": "r@x.co", "department": "QA", "joined_on": "2026-08-01"})
    pi = _ms(2026, 8, 10, 3, 58)

    def one(_):
        return TestClient(app, raise_server_exceptions=False).post(
            "/attendance/punch-in", json={"emp_code": "EMP9101", "punched_at": pi}
        ).status_code

    codes = list(ThreadPoolExecutor(max_workers=5).map(one, range(5)))
    assert codes.count(201) == 1 and codes.count(409) == 4


@needs_db
def test_leaderboard_tie_shares_rank_and_overflows_limit():
    _reset()
    for code in ("EMP9201", "EMP9202", "EMP9203"):
        c.post("/employees", json={"emp_code": code, "name": "T", "email": "t@x.co", "department": "QAT", "joined_on": "2026-08-01"})
        pi = _ms(2026, 8, 11, 4, 35)
        c.post("/attendance/punch-in", json={"emp_code": code, "punched_at": pi})
        c.post("/attendance/punch-out", json={"emp_code": code, "punched_at": pi + 9 * 3600 * 1000})
    r = c.get("/analytics/leaderboard/late", params={"month": "2026-08", "limit": 1, "department": "QAT"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 3 and all(it["rank"] == 1 for it in items)


@needs_db
def test_zero_log_employee_counts_in_headcount():
    _reset()
    c.post("/employees", json={"emp_code": "EMP9301", "name": "Z", "email": "z@x.co", "department": "QAZ", "joined_on": "2026-07-01"})
    r = c.get("/analytics/departments/summary", params={"month": "2026-07", "department": "QAZ"})
    assert r.status_code == 200
    (item,) = r.json()["items"]
    assert item["headcount"] == 1 and item["present_days"] == 0 and item["avg_work_hours"] is None
