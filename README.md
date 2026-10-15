# Employee Attendance & Analytics API

FastAPI + MongoDB backend: employees punch in/out with shift rules, managers correct records with an audit trail, and four analytics endpoints answer from MongoDB aggregations. Built for the HROne engineering assignment (Contract v2.0); all behavior follows the contract's business rules R1–R10.

## Prerequisites
- Python 3.11+
- MongoDB 6.0+ (7.0 used by the grader), reachable at `MONGO_URI`
- `pip`

## Setup
```powershell
Set-Location -LiteralPath "<repo>"
python -m venv .venv
.\.venv\Scripts\Activate
pip install -r requirements.txt
```

## Configuration
| Variable | Purpose, no values here |
|---|---|
| `MONGO_URI` | Connection string (local `mongodb://localhost:27017` or Atlas). Real environment wins over `.env`. |
| `MONGO_DB` | Database name holding `employees` + `attendance_logs`. |

A local `.env` with these two names is fine for development. Never commit it. Indexes are created at startup, idempotently; `GET /health` (which pings Mongo) tells you whether the app sees the database. Note: `TestClient` skips lifespan, so the test suite calls `ensure_indexes()` itself.

## Sample data
The kit ships nine shape-only documents plus `sample_seed.py` (outside this repo). With Mongo running, from the kit folder:
```powershell
$env:MONGO_URI = "mongodb://localhost:27017"
$env:MONGO_DB = "attendance_db"
python sample_seed.py
```
The grader seeds a larger hidden dataset with ties, weekend records, zero-log employees, and mid-month joiners — passing on the sample proves shapes, not analytics.

## Run
```powershell
python -m uvicorn app.main:app --port 8000
```
Ready when `GET /health` returns `200 {"status":"ok"}` (within ~20s). `503` means Mongo is unreachable. Interactive docs: `http://127.0.0.1:8000/docs`.

## Tests
```powershell
python -m pytest tests -q
```
15 tests: 7 pure rule checks (`test_rules.py`, no DB) + 4 contract-validation checks (`test_api.py`, no DB) + 4 live checks (`test_live.py`, skipped without MongoDB: parallel-race uniqueness, leaderboard tie overflow, zero-log headcount, PATCH history content + recompute). Requires a live MongoDB for the last four.

## API
- `GET /health` — pings Mongo (`200`/`503`)
- `POST/GET /employees` — create (`201`/`409`/`422`) and filtered (exact department), sorted (`emp_code` asc), paginated list
- `POST /attendance/punch-in` (`201`/`404`/`409`/`422`) and `POST /attendance/punch-out` (`200`/`404`/`409`/`422`)
- `GET /attendance` — `emp_code`/date/status filters, `date` desc + `emp_code` asc, DB-side pagination
- `PATCH /attendance/{emp_code}/{date}` — regularization with a single history append (`422` on no-change, `409` on concurrent edit)
- Analytics over stored derived values: employee monthly, department summary, late leaderboard (competition rank), department trend (gap-filled + 7d average)
- `GET /admin/explain/{endpoint}` — raw `executionStats` plans; all five verified `IXSCAN`, no `COLLSCAN`

## Status and limits
Implemented: all 12 endpoints, R1–R10, concurrency guards (unique-index races, atomic closes, history-length-guarded PATCH), startup indexes. Honest limits: pipelines do the grouping/windowing while final 2/4-decimal rounding happens in Python (exact half-up); trend day-rows are generated in-DB (`$range` + `$unwind` over the department's own document — needs MongoDB 5.1+); no auth, no holiday calendar (Mon–Fri per R7).
