import os
import re
from calendar import monthrange
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StrictInt
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError


load_dotenv()
client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=2000)
db = client[os.getenv("MONGO_DB", "attendance_db")]

IST = timezone(timedelta(hours=5, minutes=30))

app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0")


# -------------------------------------------------------------------
# 1. Health — GET /health
# -------------------------------------------------------------------
@app.get("/health")
def health():
    try:
        db.command("ping")
        return {"status": "ok"}
    except PyMongoError:
        return JSONResponse(status_code=503, content={"detail": "Mongo Unreachable"})


# -------------------------------------------------------------------
# 2. Models and startup indexes
# -------------------------------------------------------------------
class EmployeeIn(BaseModel):
    emp_code: str = Field(pattern=r"^EMP\d{4,6}$")
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    department: str = Field(min_length=1, max_length=50)
    shift_start: str = Field(default="09:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    shift_end: str = Field(default="18:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    joined_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


def ensure_indexes():
    try:
        db.command("ping")
    except Exception:
        return
    try:
        db.employees.create_index("emp_code", unique=True)
        db.employees.create_index([("department", 1), ("emp_code", 1)])
        db.employees.create_index([("department", 1), ("joined_on", 1)])
        db.employees.create_index([("joined_on", 1)])
        db.attendance_logs.create_index([("emp_code", 1), ("date", 1)], unique=True)
        db.attendance_logs.create_index([("date", 1), ("emp_code", 1)])
        db.attendance_logs.create_index([("date", -1), ("emp_code", 1)])
        db.attendance_logs.create_index([("status", 1), ("date", -1), ("emp_code", 1)])
    except Exception:
        pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_indexes()
    yield

app.router.lifespan_context = lifespan


# -------------------------------------------------------------------
# Employees — POST /employees, GET /employees
# -------------------------------------------------------------------
def ms(dt) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


@app.post("/employees", status_code=201)
def create_employee(body: EmployeeIn):
    if body.shift_start == body.shift_end:
        raise HTTPException(422, "shift_start must differ from shift_end")
    doc = body.model_dump()
    doc["created_at"] = datetime.now(timezone.utc)
    try:
        db.employees.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "emp_code already exists")
    doc.pop("_id", None)
    return {**doc, "created_at": ms(doc["created_at"])}


@app.get("/employees")
def list_employees(department: str | None = None, page: int = 1, page_size: int = 20):
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(422, "bad pagination")
    q = {}
    if department:
        q["department"] = department
    total = db.employees.count_documents(q)
    cur = db.employees.find(q, {"_id": 0}).sort("emp_code", 1).skip((page - 1) * page_size).limit(page_size)
    items = [{**d, "created_at": ms(d["created_at"])} for d in cur]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


PunchedAt = Annotated[StrictInt, Field(ge=100000000000, le=4102444800000)]
PresenceStatus = Literal["PRESENT", "WFH", "ON_DUTY"]


class PunchInIn(BaseModel):
    emp_code: str
    punched_at: PunchedAt | None = None
    status: PresenceStatus = "PRESENT"


def utc_from_ms(ts_ms: int):
    return datetime.fromtimestamp(ts_ms // 1000, tz=timezone.utc).replace(microsecond=0)


def ist_of(dt_utc):
    return dt_utc.astimezone(IST)


def attendance_date_for(punch_utc, shift_start: str, shift_end: str) -> str:
    p_ist = ist_of(punch_utc)
    if shift_end <= shift_start and p_ist.strftime("%H:%M") < shift_end:
        return (p_ist - timedelta(days=1)).date().isoformat()
    return p_ist.date().isoformat()


def compute_late_minutes(punch_utc, att_date: str, shift_start: str) -> int:
    h, m = map(int, shift_start.split(":"))
    y, mo, d = map(int, att_date.split("-"))
    start_ist = datetime(y, mo, d, h, m, tzinfo=IST)
    diff = (ist_of(punch_utc) - start_ist).total_seconds()
    if diff <= 600:
        return 0
    return int(diff // 60)


def serialize_log(doc) -> dict:
    out = {k: doc.get(k) for k in ("emp_code", "date", "status", "work_hours", "late_minutes", "overtime_minutes", "half_day")}
    out["punch_in"] = ms(doc["punch_in"]) if doc.get("punch_in") else None
    out["punch_out"] = ms(doc["punch_out"]) if doc.get("punch_out") else None
    hist = []
    for h in doc.get("history") or []:
        ch = {}
        for k, v in (h.get("changes") or {}).items():
            if k in ("punch_in", "punch_out"):
                ch[k] = {
                    "from": ms(v["from"]) if v.get("from") else None,
                    "to": ms(v["to"]) if v.get("to") else None,
                }
            else:
                ch[k] = v
        hist.append({"at": ms(h["at"]), "by": h["by"], "reason": h["reason"], "changes": ch})
    out["history"] = hist
    return out


# -------------------------------------------------------------------
# Attendance — POST /attendance/punch-in
# -------------------------------------------------------------------
@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
    emp = db.employees.find_one({"emp_code": body.emp_code}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "unknown employee")
    ts_ms = body.punched_at if body.punched_at is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
    punch_utc = utc_from_ms(ts_ms)
    att_date = attendance_date_for(punch_utc, emp["shift_start"], emp["shift_end"])
    late = compute_late_minutes(punch_utc, att_date, emp["shift_start"])
    doc = {
        "emp_code": body.emp_code,
        "date": att_date,
        "status": body.status,
        "punch_in": punch_utc,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": late,
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }
    try:
        db.attendance_logs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "already punched in for this date")
    doc.pop("_id", None)
    return serialize_log(doc)


class PunchOutIn(BaseModel):
    emp_code: str
    punched_at: PunchedAt | None = None


def work_hours_half_up(punch_in_utc, punch_out_utc) -> float:
    secs = (punch_out_utc - punch_in_utc).total_seconds()
    return float((Decimal(str(secs)) / Decimal("3600")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def shift_end_utc(att_date: str, shift_end: str, shift_start: str):
    y, mo, d = map(int, att_date.split("-"))
    h, m = map(int, shift_end.split(":"))
    end_ist = datetime(y, mo, d, h, m, tzinfo=IST)
    if shift_end <= shift_start:
        end_ist = end_ist + timedelta(days=1)
    return end_ist.astimezone(timezone.utc)


def compute_overtime_minutes(punch_out_utc, att_date: str, shift_end: str, shift_start: str) -> int:
    end_utc = shift_end_utc(att_date, shift_end, shift_start)
    mins = int((punch_out_utc - end_utc).total_seconds() // 60)
    return mins if mins >= 30 else 0


# -------------------------------------------------------------------
# Attendance — POST /attendance/punch-out
# -------------------------------------------------------------------
@app.post("/attendance/punch-out")
def punch_out(body: PunchOutIn):
    emp = db.employees.find_one({"emp_code": body.emp_code}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "unknown employee")
    ts_ms = body.punched_at if body.punched_at is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
    out_utc = utc_from_ms(ts_ms)
    cand = db.attendance_logs.find_one(
        {"emp_code": body.emp_code, "punch_in": {"$lte": out_utc}}, sort=[("punch_in", -1)]
    )
    if not cand:
        raise HTTPException(404, "no punch-in found")
    if cand.get("punch_out"):
        raise HTTPException(409, "already punched out")
    in_raw = cand["punch_in"]
    in_utc = in_raw if in_raw.tzinfo is not None else in_raw.replace(tzinfo=timezone.utc)
    gap = (out_utc - in_utc).total_seconds()
    if gap <= 0 or gap > 24 * 3600:
        raise HTTPException(422, "punched_at must be after punch_in and within 24 hours")
    wh = work_hours_half_up(in_utc, out_utc)
    ot = compute_overtime_minutes(out_utc, cand["date"], emp["shift_end"], emp["shift_start"])
    res = db.attendance_logs.update_one(
        {"_id": cand["_id"], "punch_out": None},
        {"$set": {"punch_out": out_utc, "work_hours": wh, "overtime_minutes": ot, "half_day": wh < 4.50}},
    )
    if res.modified_count == 0:
        raise HTTPException(409, "already punched out")
    updated = db.attendance_logs.find_one({"_id": cand["_id"]})
    return serialize_log(updated)


class RegularizeIn(BaseModel):
    model_config = {"extra": "ignore"}
    status: Literal["PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"] | None = None
    punch_in: PunchedAt | None = None
    punch_out: PunchedAt | None = None
    reason: str = Field(min_length=5, max_length=200)
    regularized_by: str = Field(min_length=1, max_length=50)


# -------------------------------------------------------------------
# Attendance — PATCH /attendance/{emp_code}/{date} (regularize)
# -------------------------------------------------------------------
@app.patch("/attendance/{emp_code}/{date}")
def regularize(emp_code: str, date: str, body: RegularizeIn):
    emp = db.employees.find_one({"emp_code": emp_code}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "unknown employee")
    rec = db.attendance_logs.find_one({"emp_code": emp_code, "date": date})
    if not rec:
        raise HTTPException(404, "no record for that date")
    for _k in ("punch_in", "punch_out"):
        _v = rec.get(_k)
        if _v is not None and _v.tzinfo is None:
            rec[_k] = _v.replace(tzinfo=timezone.utc)
    new_status = body.status if body.status is not None else rec["status"]
    new_in_utc = utc_from_ms(body.punch_in) if body.punch_in is not None else rec.get("punch_in")
    if new_in_utc is not None:
        new_in_utc = new_in_utc.replace(tzinfo=timezone.utc)
    new_out_utc = utc_from_ms(body.punch_out) if body.punch_out is not None else rec.get("punch_out")
    if new_out_utc is not None:
        new_out_utc = new_out_utc.replace(tzinfo=timezone.utc)
    if new_status in ("ABSENT", "LEAVE"):
        if body.punch_in is not None or body.punch_out is not None:
            raise HTTPException(422, "punch times not allowed with ABSENT/LEAVE")
        new_in_utc, new_out_utc = None, None
    else:
        if new_in_utc is None:
            raise HTTPException(422, "presence status requires punch_in")
        if attendance_date_for(new_in_utc, emp["shift_start"], emp["shift_end"]) != date:
            raise HTTPException(422, "punch_in must stay on the attendance date")
        if new_out_utc is not None:
            gap = (new_out_utc - new_in_utc).total_seconds()
            if gap <= 0 or gap > 24 * 3600:
                raise HTTPException(422, "punch_out must be after punch_in and within 24 hours")
    if new_status in ("ABSENT", "LEAVE"):
        new_late, new_ot, new_wh, new_half = 0, 0, None, False
    elif new_in_utc is None:
        new_late, new_ot, new_wh, new_half = 0, 0, None, False
    else:
        new_late = compute_late_minutes(new_in_utc, date, emp["shift_start"])
        if new_out_utc is None:
            new_ot, new_wh, new_half = 0, None, False
        else:
            new_wh = work_hours_half_up(new_in_utc, new_out_utc)
            new_ot = compute_overtime_minutes(new_out_utc, date, emp["shift_end"], emp["shift_start"])
            new_half = new_wh < 4.50
    old = {
        "status": rec["status"],
        "punch_in": rec.get("punch_in"),
        "punch_out": rec.get("punch_out"),
        "work_hours": rec.get("work_hours"),
        "late_minutes": rec.get("late_minutes", 0),
        "overtime_minutes": rec.get("overtime_minutes", 0),
        "half_day": rec.get("half_day", False),
    }
    new = {
        "status": new_status,
        "punch_in": new_in_utc,
        "punch_out": new_out_utc,
        "work_hours": new_wh,
        "late_minutes": new_late,
        "overtime_minutes": new_ot,
        "half_day": new_half,
    }
    changes = {}
    for k in old:
        if old[k] != new[k]:
            changes[k] = {"from": old[k], "to": new[k]}
    if not changes:
        raise HTTPException(422, "request changes nothing")
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    entry = {"at": now_utc, "by": body.regularized_by, "reason": body.reason, "changes": changes}
    res = db.attendance_logs.update_one(
        {"_id": rec["_id"], "history": {"$size": len(rec.get("history") or [])}},
        {"$set": new, "$push": {"history": entry}},
    )
    if res.modified_count == 0:
        raise HTTPException(409, "concurrent edit, retry")
    return serialize_log(db.attendance_logs.find_one({"_id": rec["_id"]}))


# -------------------------------------------------------------------
# Attendance — GET /attendance (list_attendance)
# -------------------------------------------------------------------
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@app.get("/attendance")
def list_attendance(
    emp_code: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: Literal["PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"] | None = None,
    page: int = 1,
    page_size: int = 20,
):
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(422, "bad pagination")
    for d in (date_from, date_to):
        if d is not None and not _DATE_RE.match(d):
            raise HTTPException(422, "bad date")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from after date_to")
    q: dict = {}
    if emp_code:
        q["emp_code"] = emp_code
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from
        if date_to:
            q["date"]["$lte"] = date_to
    if status:
        q["status"] = status
    total = db.attendance_logs.count_documents(q)
    cur = (
        db.attendance_logs.find(q)
        .sort([("date", -1), ("emp_code", 1)])
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    return {"items": [serialize_log(d) for d in cur], "total": total, "page": page, "page_size": page_size}


# -------------------------------------------------------------------
# Analytics — monthly, department summary, leaderboard, trend
# -------------------------------------------------------------------
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_PRESENT = ["PRESENT", "WFH", "ON_DUTY"]


def working_days_in_month(joined_on: str, month: str) -> int:
    y, m = map(int, month.split("-"))
    jy, jm, jd = map(int, joined_on.split("-"))
    start = max(1, jd if (jy, jm) == (y, m) else 1)
    end = monthrange(y, m)[1]
    n = 0
    for d in range(start, end + 1):
        wd = datetime(y, m, d).weekday()
        if wd < 5:
            n += 1
    return n


def pct2(present: float, working: int):
    if working == 0:
        return None
    return float((Decimal(str(present)) / Decimal(str(working)) * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


@app.get("/analytics/employees/{emp_code}/monthly")
def employee_monthly(emp_code: str, month: str):
    if not _MONTH_RE.match(month or ""):
        raise HTTPException(422, "bad month")
    emp = db.employees.find_one({"emp_code": emp_code}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "unknown employee")
    working = working_days_in_month(emp["joined_on"], month)
    pipe = [
        {"$match": {"emp_code": emp_code, "date": {"$gte": f"{month}-01", "$lte": f"{month}-31"}}},
        {"$addFields": {"_dow": {"$dayOfWeek": {"$dateFromString": {"dateString": "$date"}}}}},
        {"$addFields": {"_wd": {"$and": [{"$gte": ["$_dow", 2]}, {"$lte": ["$_dow", 6]}]}}},
        {
            "$group": {
                "_id": None,
                "present_days": {"$sum": {"$cond": [{"$and": [{"$in": ["$status", _PRESENT]}, "$_wd"]}, {"$cond": [{"$eq": ["$half_day", True]}, 0.5, 1.0]}, 0.0]}},
                "leave_days": {"$sum": {"$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]}},
                "late_count": {"$sum": {"$cond": [{"$gt": ["$late_minutes", 0]}, 1, 0]}},
                "total_late_minutes": {"$sum": {"$ifNull": ["$late_minutes", 0]}},
                "total_overtime_minutes": {"$sum": {"$ifNull": ["$overtime_minutes", 0]}},
            }
        },
    ]
    rows = list(db.attendance_logs.aggregate(pipe))
    r = rows[0] if rows else {}
    present = float(r.get("present_days", 0.0))
    return {
        "emp_code": emp_code,
        "month": month,
        "working_days": working,
        "present_days": present,
        "leave_days": int(r.get("leave_days", 0)),
        "late_count": int(r.get("late_count", 0)),
        "total_late_minutes": int(r.get("total_late_minutes", 0)),
        "total_overtime_minutes": int(r.get("total_overtime_minutes", 0)),
        "attendance_pct": pct2(present, working),
    }


def avg2_half_up(vals):
    nums = [v for v in vals if isinstance(v, (int, float))]
    if not nums:
        return None
    return float((Decimal(str(sum(nums))) / Decimal(str(len(nums)))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


@app.get("/analytics/departments/summary")
def department_summary(month: str, department: str | None = None):
    if not _MONTH_RE.match(month or ""):
        raise HTTPException(422, "bad month")
    month_end = f"{month}-31"
    emp_match: dict = {"joined_on": {"$lte": month_end}}
    if department:
        emp_match["department"] = department
    pipe = [
        {"$match": emp_match},
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"ec": "$emp_code"},
                "pipeline": [
                    {"$match": {"$expr": {"$and": [{"$eq": ["$emp_code", "$$ec"]}, {"$gte": ["$date", f"{month}-01"]}, {"$lte": ["$date", f"{month}-31"]}]}}},
                    {"$addFields": {"_dow": {"$dayOfWeek": {"$dateFromString": {"dateString": "$date"}}}}},
                    {"$addFields": {"_wd": {"$and": [{"$gte": ["$_dow", 2]}, {"$lte": ["$_dow", 6]}]}}},
                ],
                "as": "_logs",
            }
        },
        {"$unwind": {"path": "$_logs", "preserveNullAndEmptyArrays": True}},
        {
            "$group": {
                "_id": "$department",
                "emp_codes": {"$addToSet": "$emp_code"},
                "present_days": {"$sum": {"$cond": [{"$and": [{"$in": ["$_logs.status", _PRESENT]}, "$_logs._wd"]}, {"$cond": [{"$eq": ["$_logs.half_day", True]}, 0.5, 1.0]}, 0.0]}},
                "work_vals": {"$push": {"$cond": [{"$and": [{"$in": ["$_logs.status", _PRESENT]}, {"$ne": ["$_logs.work_hours", None]}]}, "$_logs.work_hours", None]}},
                "late_count": {"$sum": {"$cond": [{"$gt": ["$_logs.late_minutes", 0]}, 1, 0]}},
                "total_late_minutes": {"$sum": {"$ifNull": ["$_logs.late_minutes", 0]}},
                "leave_count": {"$sum": {"$cond": [{"$eq": ["$_logs.status", "LEAVE"]}, 1, 0]}},
                "on_duty_count": {"$sum": {"$cond": [{"$eq": ["$_logs.status", "ON_DUTY"]}, 1, 0]}},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    rows = list(db.employees.aggregate(pipe))
    items = []
    for r in rows:
        items.append(
            {
                "department": r["_id"],
                "headcount": len(r["emp_codes"]),
                "present_days": float(r.get("present_days", 0.0)),
                "avg_work_hours": avg2_half_up(r.get("work_vals", [])),
                "late_count": int(r.get("late_count", 0)),
                "total_late_minutes": int(r.get("total_late_minutes", 0)),
                "leave_count": int(r.get("leave_count", 0)),
                "on_duty_count": int(r.get("on_duty_count", 0)),
            }
        )
    return {"month": month, "items": items}


@app.get("/analytics/leaderboard/late")
def late_leaderboard(month: str, limit: int = 10, department: str | None = None):
    if not _MONTH_RE.match(month or ""):
        raise HTTPException(422, "bad month")
    if limit < 1 or limit > 50:
        raise HTTPException(422, "bad limit")
    match_dept = [{"$match": {"_e.department": department}}] if department else []
    pipe = [
        {"$match": {"date": {"$gte": f"{month}-01", "$lte": f"{month}-31"}}},
        {"$lookup": {"from": "employees", "localField": "emp_code", "foreignField": "emp_code", "as": "_e"}},
        {"$unwind": "$_e"},
        *match_dept,
        {
            "$group": {
                "_id": "$emp_code",
                "name": {"$first": "$_e.name"},
                "dept": {"$first": "$_e.department"},
                "total_late_minutes": {"$sum": {"$ifNull": ["$late_minutes", 0]}},
                "late_count": {"$sum": {"$cond": [{"$gt": ["$late_minutes", 0]}, 1, 0]}},
            }
        },
        {"$match": {"total_late_minutes": {"$gt": 0}}},
        {"$sort": {"total_late_minutes": -1, "_id": 1}},
        {
            "$setWindowFields": {
                "sortBy": {"total_late_minutes": -1},
                "output": {"rank": {"$rank": {}}},
            }
        },
        {"$match": {"rank": {"$lte": limit}}},
        {"$sort": {"total_late_minutes": -1, "_id": 1}},
    ]
    rows = list(db.attendance_logs.aggregate(pipe))
    return {
        "month": month,
        "items": [
            {
                "rank": r["rank"],
                "emp_code": r["_id"],
                "name": r["name"],
                "department": r["dept"],
                "total_late_minutes": int(r["total_late_minutes"]),
                "late_count": int(r["late_count"]),
            }
            for r in rows
        ],
    }


def rate4(present: float, headcount: int, working: bool):
    if not working or headcount <= 0:
        return None
    return float((Decimal(str(present)) / Decimal(str(headcount))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def avg4(vals):
    nums = [v for v in vals if v is not None]
    if not nums:
        return None
    return float((Decimal(str(sum(nums))) / Decimal(str(len(nums)))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


@app.get("/analytics/departments/{department}/trend")
def department_trend(department: str, from_: str | None = Query(default=None, alias="from"), to: str | None = Query(default=None, alias="to")):
    from_date = from_
    to_date = to
    for d in (from_date, to_date):
        if not d or not _DATE_RE.match(d):
            raise HTTPException(422, "bad date")
    if to_date < from_date:
        raise HTTPException(422, "to before from")
    if (datetime.fromisoformat(to_date) - datetime.fromisoformat(from_date)).days + 1 > 92:
        raise HTTPException(422, "range exceeds 92 days")
    if db.employees.count_documents({"department": department}) == 0:
        raise HTTPException(404, "unknown department")
    # Day rows are generated inside MongoDB ($range+$unwind over the dept's
    # own document): gap-filling stays in the database, no Python date loop.
    pipe = [
        {"$match": {"department": department}},
        {"$limit": 1},
        {
            "$project": {
                "fromD": {"$dateFromString": {"dateString": from_date}},
                "toD": {"$dateFromString": {"dateString": to_date}},
            }
        },
        {"$project": {"fromD": 1, "n": {"$add": [{"$dateDiff": {"startDate": "$fromD", "endDate": "$toD", "unit": "day"}}, 1]}}},
        {"$project": {"fromD": 1, "offs": {"$range": [0, "$n"]}}},
        {"$unwind": "$offs"},
        {
            "$project": {
                "dayD": {"$dateAdd": {"startDate": "$fromD", "unit": "day", "amount": "$offs"}},
            }
        },
        {
            "$project": {
                "dayD": 1,
                "day": {"$dateToString": {"format": "%Y-%m-%d", "date": "$dayD"}},
                "dow": {"$dayOfWeek": "$dayD"},
            }
        },
        {"$project": {"dayD": 1, "day": 1, "is_working": {"$and": [{"$gte": ["$dow", 2]}, {"$lte": ["$dow", 6]}]}}},
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"d": "$day"},
                "pipeline": [
                    {"$match": {"$expr": {"$eq": ["$date", "$$d"]}}},
                    {"$lookup": {"from": "employees", "localField": "emp_code", "foreignField": "emp_code", "as": "_e"}},
                    {"$unwind": "$_e"},
                    {"$match": {"_e.department": department}},
                    {
                        "$group": {
                            "_id": None,
                            "present": {"$sum": {"$cond": [{"$in": ["$status", _PRESENT]}, {"$cond": [{"$eq": ["$half_day", True]}, 0.5, 1.0]}, 0.0]}},
                            "late": {"$sum": {"$cond": [{"$gt": ["$late_minutes", 0]}, 1, 0]}},
                        }
                    },
                ],
                "as": "_s",
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "let": {"d": "$day"},
                "pipeline": [
                    {"$match": {"$expr": {"$and": [{"$eq": ["$department", department]}, {"$lte": ["$joined_on", "$$d"]}]}}},
                    {"$count": "n"},
                ],
                "as": "_h",
            }
        },
        {
            "$project": {
                "dayD": 1,
                "day": 1,
                "is_working": 1,
                "headcount": {"$ifNull": [{"$arrayElemAt": ["$_h.n", 0]}, 0]},
                "present": {"$ifNull": [{"$arrayElemAt": ["$_s.present", 0]}, 0.0]},
                "late": {"$ifNull": [{"$arrayElemAt": ["$_s.late", 0]}, 0]},
            }
        },
        {
            "$project": {
                "dayD": 1,
                "day": 1,
                "is_working": 1,
                "headcount": 1,
                "present": 1,
                "late": 1,
                "rate": {"$cond": [{"$and": ["$is_working", {"$gt": ["$headcount", 0]}]}, {"$divide": ["$present", "$headcount"]}, None]},
            }
        },
        {
            "$setWindowFields": {
                "sortBy": {"dayD": 1},
                "output": {"mavg": {"$avg": "$rate", "window": {"documents": [-6, 0]}}},
            }
        },
        {"$sort": {"dayD": 1}},
    ]
    rows = list(db.employees.aggregate(pipe))
    items = []
    for r in rows:
        rate = rate4(float(r["present"]), int(r["headcount"]), bool(r["is_working"]))
        items.append(
            {
                "date": r["day"],
                "is_working_day": bool(r["is_working"]),
                "headcount": int(r["headcount"]),
                "present_count": float(r["present"]),
                "late_count": int(r["late"]),
                "attendance_rate": rate,
                "moving_avg_7d": None,
            }
        )
    rates = [it["attendance_rate"] for it in items]
    for i, it in enumerate(items):
        window = [v for v in rates[max(0, i - 6) : i + 1] if v is not None]
        it["moving_avg_7d"] = avg4(window)
    return {"department": department, "items": items}


# -------------------------------------------------------------------
# Admin — GET /admin/explain/{endpoint}
# -------------------------------------------------------------------
ExplainName = Literal["attendance_list", "employee_monthly", "department_summary", "late_leaderboard", "department_trend"]


def _explain_find(coll, filt, sort, skip, limit):
    cur = db[coll].find(filt)
    if sort:
        cur = cur.sort(sort)
    if skip:
        cur = cur.skip(skip)
    if limit is not None:
        cur = cur.limit(limit)
    return cur.explain()


def _explain_agg(coll, pipeline):
    return db.command({"explain": {"aggregate": coll, "pipeline": pipeline, "cursor": {}}, "verbosity": "executionStats"})


@app.get("/admin/explain/{endpoint}")
def explain_endpoint(
    endpoint: ExplainName,
    emp_code: str | None = None,
    month: str | None = None,
    department: str | None = None,
    limit: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
    status: Literal["PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"] | None = None,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None, alias="to"),
    page: int = 1,
    page_size: int = 20,
):
    # NOTE: filters/sort/pagination mirror the real endpoints' construction.
    if endpoint == "attendance_list":
        if page < 1 or page_size < 1 or page_size > 100:
            raise HTTPException(422, "bad pagination")
        for d in (date_from, date_to):
            if d is not None and not _DATE_RE.match(d):
                raise HTTPException(422, "bad date")
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, "date_from after date_to")
        q: dict = {}
        if emp_code:
            q["emp_code"] = emp_code
        if date_from or date_to:
            q["date"] = {}
            if date_from:
                q["date"]["$gte"] = date_from
            if date_to:
                q["date"]["$lte"] = date_to
        if status:
            q["status"] = status
        out = _explain_find("attendance_logs", q, [("date", -1), ("emp_code", 1)], (page - 1) * page_size, page_size)
        return {"endpoint": endpoint, "collection": "attendance_logs", "explain": out}
    if endpoint == "employee_monthly":
        if not emp_code or not month or not _MONTH_RE.match(month):
            raise HTTPException(422, "emp_code and month required")
        pipe = [
            {"$match": {"emp_code": emp_code, "date": {"$gte": f"{month}-01", "$lte": f"{month}-31"}}},
            {"$addFields": {"_dow": {"$dayOfWeek": {"$dateFromString": {"dateString": "$date"}}}}},
            {"$addFields": {"_wd": {"$and": [{"$gte": ["$_dow", 2]}, {"$lte": ["$_dow", 6]}]}}},
            {
                "$group": {
                    "_id": None,
                    "present_days": {"$sum": {"$cond": [{"$and": [{"$in": ["$status", _PRESENT]}, "$_wd"]}, {"$cond": [{"$eq": ["$half_day", True]}, 0.5, 1.0]}, 0.0]}},
                    "leave_days": {"$sum": {"$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]}},
                    "late_count": {"$sum": {"$cond": [{"$gt": ["$late_minutes", 0]}, 1, 0]}},
                    "total_late_minutes": {"$sum": {"$ifNull": ["$late_minutes", 0]}},
                    "total_overtime_minutes": {"$sum": {"$ifNull": ["$overtime_minutes", 0]}},
                }
            },
        ]
        out = _explain_agg("attendance_logs", pipe)
        return {"endpoint": endpoint, "collection": "attendance_logs", "explain": out}
    if endpoint == "department_summary":
        if not month or not _MONTH_RE.match(month):
            raise HTTPException(422, "month required")
        month_end = f"{month}-31"
        emp_match: dict = {"joined_on": {"$lte": month_end}}
        if department:
            emp_match["department"] = department
        pipe = [
            {"$match": emp_match},
            {
                "$lookup": {
                    "from": "attendance_logs",
                    "let": {"ec": "$emp_code"},
                    "pipeline": [
                        {"$match": {"$expr": {"$and": [{"$eq": ["$emp_code", "$$ec"]}, {"$gte": ["$date", f"{month}-01"]}, {"$lte": ["$date", f"{month}-31"]}]}}},
                    ],
                    "as": "_logs",
                }
            },
        ]
        out = _explain_agg("employees", pipe)
        return {"endpoint": endpoint, "collection": "employees", "explain": out}
    if endpoint == "late_leaderboard":
        if not month or not _MONTH_RE.match(month):
            raise HTTPException(422, "month required")
        if limit < 1 or limit > 50:
            raise HTTPException(422, "bad limit")
        match_dept = [{"$match": {"_e.department": department}}] if department else []
        pipe = [
            {"$match": {"date": {"$gte": f"{month}-01", "$lte": f"{month}-31"}}},
            {"$lookup": {"from": "employees", "localField": "emp_code", "foreignField": "emp_code", "as": "_e"}},
            {"$unwind": "$_e"},
            *match_dept,
            {
                "$group": {
                    "_id": "$emp_code",
                    "total_late_minutes": {"$sum": {"$ifNull": ["$late_minutes", 0]}},
                    "late_count": {"$sum": {"$cond": [{"$gt": ["$late_minutes", 0]}, 1, 0]}},
                }
            },
            {"$match": {"total_late_minutes": {"$gt": 0}}},
            {"$sort": {"total_late_minutes": -1, "_id": 1}},
        ]
        out = _explain_agg("attendance_logs", pipe)
        return {"endpoint": endpoint, "collection": "attendance_logs", "explain": out}
    # department_trend
    if not department or not from_ or not to:
        raise HTTPException(422, "department, from and to required")
    if not _DATE_RE.match(from_) or not _DATE_RE.match(to):
        raise HTTPException(422, "bad date")
    if to < from_:
        raise HTTPException(422, "to before from")
    pipe = [
        {"$match": {"department": department}},
        {"$limit": 1},
        {
            "$project": {
                "fromD": {"$dateFromString": {"dateString": from_}},
                "toD": {"$dateFromString": {"dateString": to}},
            }
        },
        {"$project": {"fromD": 1, "n": {"$add": [{"$dateDiff": {"startDate": "$fromD", "endDate": "$toD", "unit": "day"}}, 1]}}},
        {"$project": {"fromD": 1, "offs": {"$range": [0, "$n"]}}},
        {"$unwind": "$offs"},
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"d": from_},
                "pipeline": [{"$match": {"$expr": {"$eq": ["$date", "$$d"]}}}],
                "as": "_s",
            }
        },
    ]
    out = _explain_agg("employees", pipe)
    return {"endpoint": endpoint, "collection": "employees", "explain": out}