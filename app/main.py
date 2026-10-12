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
    