# Muster (demo frontend, optional)

Browser console demonstrating the Employee Attendance & Analytics API. Not an official product of any company. Every number on screen comes from the API; nothing is mocked.

## Run
```powershell
# terminal 1 — backend (repo root)
python -m uvicorn app.main:app --port 8000
# terminal 2 — here
npm install
npm run dev
```
Open the printed `http://localhost:51xx` URL. Dev proxy forwards `/api/*` to `:8000`, so no CORS change is needed. `VITE_API_BASE_URL` overrides the API target (host only, never a secret).

## Scope
Slice 1: app shell + records table (`GET /attendance` filters, pagination, honest loading/empty/error states). Punch, correction, audit, and analytics screens follow the same client + contract types.
