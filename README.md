# Employee Attendance & Analytics API

FastAPI + MongoDB backend: employees punch in/out with shift rules, managers correct records with an audit trail, and four analytics endpoints answer from MongoDB aggregations. Built for the HROne engineering assignment (Contract v2.0); all behavior follows `openapi.yaml` R1–R10.

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

A local `.env` with these two names is fine for development. Never commit it. Indexes are created at startup, idempotently — the database may already hold data when the app boots.

## Sample data
The kit's nine shape-only documents live outside this repo. With Mongo running:
```powershell
python <kit-path>\sample_seed.py   # reads MONGO_URI / MONGO_DB, loads employees + attendance_logs
```
The grader seeds a larger hidden dataset with ties, weekend records, zero-log employees, and mid-month joiners — passing on the sample proves shapes, not analytics.

## Run
```powershell
python -m uvicorn app.main:app --port 8000
```
Ready when `GET /health` returns `200 {"status":"ok"}` (within ~20s). `503` means Mongo is unreachable. Interactive docs: `http://127.0.0.1:8000/docs`.

## Tests
```powershell
python -m pytest
```
Covers R1–R5 edge cases (grace boundaries, overnight dates, half-up rounding), punch races (unique-index `409`s), PATCH history appends, and analytics hand-counts on deterministic seeds. Requires a live MongoDB; without one, only validation (`422`) checks run.

## API
- `GET /health` — pings Mongo (`200`/`503`)
- `POST/GET /employees` — create (`201`/`409`/`422`) and filtered, sorted, paginated list
- `POST /attendance/punch-in` (`201`/`404`/`409`/`422`) and `POST /attendance/punch-out` (`200`/`404`/`409`/`422`)
- `GET /attendance` — date/status filters, `date` desc + `emp_code` asc, DB-side pagination
- `PATCH /attendance/{emp_code}/{date}` — regularization with single history append
- Analytics (all MongoDB aggregations over stored derived values): employee monthly, department summary, late leaderboard (competition rank), department trend (gap-filled + 7d average)
- `GET /admin/explain/{endpoint}` — `executionStats` plans; indexed (`IXSCAN`, no `COLLSCAN`) at ~100k records

## Status and limits
Implemented: all 12 endpoints, R1–R10, concurrency guards (unique-index races, atomic closes, history-length-guarded PATCH), startup indexes. Honest limits: final 2/4-decimal rounding happens in Python over pipeline outputs (exact half-up); trend's day enumeration uses `$documents` + `$range` (MongoDB 5.1+); no auth, no holiday calendar (Mon–Fri per R7).
