import os 
from datetime import datetime,timedelta,timezone
from dotenv import load_dotenv
from fastapi import FastAPI,HTTPException
from pymongo import MongoClient
from pymongo.errors import PyMongoError


load_dotenv()
client =MongoClient(os.getenv("MONGO_URI",  "mongodb://localhost:27017"), serverSelectionTimeoutMS=5000)
db = client[os.getenv("MONGO_DB","attendance_db")]

IST = timezone(timedelta(hours=5,minutes=30))

app=FastAPI(title = "Employee Attendance & Analytics API" ,version="2.0.0")


@app.get('/health')
def health():
    try:
        db.command("ping")
        return {"status" : "ok"}
    except PyMongoError:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503,content={"detail":"Mongo Unreachable"})


from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError
from contextlib import asynccontextmanager



class EmployeeIn(BaseModel):
    emp_code: str = Field(pattern =r"^EMP\d{4,6}$")
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    department: str = Field(min_length=1, max_length=50)
    shift_start: str = Field(default="09:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    shift_end: str = Field(default="18:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    joined_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


def ensure_indexes():
    try:
        db.employees.create_index("emp_code", unique=True)
        db.employees.create_index([("department", 1), ("emp_code", 1)])
        db.attendance_logs.create_index([("emp_code", 1), ("date", 1)], unique=True)
        db.attendance_logs.create_index([("date", 1), ("emp_code", 1)])
    except Exception:
        pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_indexes()
    yield

app.router.lifespan_context =lifespan
def ms(dt) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp()*1000)


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