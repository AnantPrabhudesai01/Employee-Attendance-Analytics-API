import os 
from datetime import datetime,timedelta,timezone
from dotenv import load_dotenv
from fastapi import FastAPI,HTTPException
from pymongo import MongoClient
from pymongo.errors import PyMongoError


load_dotenv()
client =MongoClient(os.getenv("MONGO_URI",  "mongodb://localhost:27017"))
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
    db.employees.create_index("emp_code", unique=True)
    db.employees.create_index([("department",1),("emp_code",1)])

@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_indexes()
    yield

app.router.lifespan_context =lifespan