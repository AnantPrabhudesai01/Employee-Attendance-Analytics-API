import { useState } from "react";
import { Link, NavLink, Route, BrowserRouter as Router, Routes } from "react-router";
import { apiFetch, AppError } from "./api/client";
import type { AttendancePage } from "./api/types";
import { Card, EmptyPanel, ErrorPanel, Field, GhostButton, Metric, PageHeader, PrimaryButton, SkeletonKpis, SkeletonTable, StatusBadge, inputCls } from "./components/ui";
import { fmtIST, useRequest } from "./hooks/useRequest";

/* ---------------- shell ---------------- */

const NAV = [
  { to: "/", label: "Overview", end: true },
  { to: "/attendance", label: "Attendance" },
  { to: "/punch", label: "Punch desk" },
];

/* ---------------- overview (GET /analytics/departments/summary + recent) ---------------- */

interface DeptRow {
  department: string; headcount: number; present_days: number; avg_work_hours: number | null;
  late_count: number; total_late_minutes: number; leave_count: number; on_duty_count: number;
}

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function OverviewPage() {
  const [month, setMonth] = useState("2026-07");
  const summary = useRequest(() => apiFetch<{ month: string; items: DeptRow[] }>(`/analytics/departments/summary?month=${month}`), [month]);
  const recent = useRequest(() => apiFetch<AttendancePage>("/attendance?page_size=8"), []);

  const totals = summary.data ? {
    head: summary.data.items.reduce((a, r) => a + r.headcount, 0),
    present: summary.data.items.reduce((a, r) => a + r.present_days, 0),
    late: summary.data.items.reduce((a, r) => a + r.late_count, 0),
    leave: summary.data.items.reduce((a, r) => a + r.leave_count, 0),
  } : null;

  return (
    <section aria-label="Overview">
      <PageHeader
        title="Overview"
        desc={`Department health for ${month} · source: GET /analytics/departments/summary`}
        action={
          <label className="text-sm font-medium">Month <input type="month" value={month} onChange={(e) => setMonth(e.target.value || currentMonth())} className="ml-1 rounded-lg border border-line bg-white px-2 py-1.5" /></label>
        }
      />
      {summary.status === "loading" && <SkeletonKpis />}
      {summary.status === "error" && <ErrorPanel message={summary.error instanceof AppError ? summary.error.message : "Summary failed."} onRetry={() => void summary.refetch()} />}
      {summary.status === "success" && summary.data && totals && (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Headcount" value={String(totals.head)} context="Joined on or before month-end (R9)" />
            <Metric label="Present days" value={String(totals.present)} context="Half day = 0.5 (R5)" to="/attendance" />
            <Metric label="Late arrivals" value={String(totals.late)} context="Records with late_minutes > 0" />
            <Metric label="On leave" value={String(totals.leave)} context="LEAVE records" />
          </div>
          <Card className="mt-4 overflow-hidden">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-line text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="px-4 py-2.5">Department</th><th className="px-4 py-2.5">Head</th><th className="px-4 py-2.5">Present</th>
                <th className="px-4 py-2.5">Avg h</th><th className="px-4 py-2.5">Late</th>
              </tr></thead>
              <tbody>
                {summary.data.items.map((r) => (
                  <tr key={r.department} className="border-b border-line last:border-0">
                    <td className="px-4 py-2.5 font-semibold">{r.department}</td>
                    <td className="px-4 py-2.5">{r.headcount}</td>
                    <td className="px-4 py-2.5">{r.present_days}</td>
                    <td className="px-4 py-2.5">{r.avg_work_hours ?? "—"}</td>
                    <td className="px-4 py-2.5">{r.late_count} <span className="text-slate-400">({r.total_late_minutes}m)</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
      <h2 className="mb-2 mt-6 text-lg font-semibold">Recent records</h2>
      {recent.status === "loading" && <SkeletonTable rows={4} />}
      {recent.status === "error" && <ErrorPanel message="Recent records failed." onRetry={() => void recent.refetch()} />}
      {recent.status === "success" && recent.data && (
        <Card className="overflow-hidden">
          {recent.data.items.map((r) => (
            <div key={`${r.emp_code}-${r.date}`} className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5 text-sm last:border-0">
              <span className="font-medium">{r.emp_code} <span className="font-normal text-slate-500">{r.date}</span></span>
              <span className="flex items-center gap-2"><StatusBadge status={r.status} /><span className="text-slate-500">{fmtIST(r.punch_in)}</span></span>
            </div>
          ))}
        </Card>
      )}
      <p className="mt-3 text-sm"><Link to="/attendance" className="font-medium text-brand hover:underline">View all records →</Link></p>
    </section>
  );
}

/* ---------------- attendance records ---------------- */

function RecordsPage() {
  const [emp, setEmp] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);

  const q = new URLSearchParams({ page: String(page), page_size: "20" });
  if (emp) q.set("emp_code", emp);
  if (from) q.set("date_from", from);
  if (to) q.set("date_to", to);
  if (status) q.set("status", status);

  const { status: st, data, error, isRefreshing, refetch } = useRequest<AttendancePage>(
    () => apiFetch<AttendancePage>(`/attendance?${q.toString()}`),
    [emp, from, to, status, page],
  );

  return (
    <section aria-label="Attendance records">
      <PageHeader
        title="Attendance records"
        desc={data ? `Total ${data.total} (server count)` : "Filters map 1:1 to GET /attendance."}
        action={<GhostButton onClick={() => void refetch()} disabled={isRefreshing}>{isRefreshing ? "Refreshing…" : "Refresh"}</GhostButton>}
      />
      <form className="mb-4 grid grid-cols-2 gap-3 rounded-xl border border-line bg-white p-4 md:grid-cols-5"
        onSubmit={(e) => { e.preventDefault(); setPage(1); void refetch(); }}>
        <Field label="Employee" hint="Exact code"><input value={emp} onChange={(e) => setEmp(e.target.value)} placeholder="EMP0001" className={inputCls} /></Field>
        <Field label="From"><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className={inputCls} /></Field>
        <Field label="To"><input type="date" value={to} onChange={(e) => setTo(e.target.value)} className={inputCls} /></Field>
        <Field label="Status"><select value={status} onChange={(e) => setStatus(e.target.value)} className={inputCls}>
          <option value="">All</option><option>PRESENT</option><option>WFH</option><option>ON_DUTY</option><option>ABSENT</option><option>LEAVE</option>
        </select></Field>
        <div className="flex items-end gap-2">
          <PrimaryButton type="submit">Apply</PrimaryButton>
          <button type="button" onClick={() => { setEmp(""); setFrom(""); setTo(""); setStatus(""); setPage(1); }} className="rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100">Reset</button>
        </div>
      </form>

      {st === "loading" && <SkeletonTable />}
      {st === "error" && <ErrorPanel message={error instanceof AppError ? error.message : "Request failed."} onRetry={() => void refetch()} />}
      {st === "success" && data && (
        data.items.length === 0 ? <EmptyPanel text="No records for these filters." /> : (
          <>
            <Card className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead><tr className="border-b border-line text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-3 py-2">Employee</th><th className="px-3 py-2">Date</th><th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">In</th><th className="px-3 py-2">Out</th><th className="px-3 py-2">Work h</th><th className="px-3 py-2">Late</th>
                </tr></thead>
                <tbody>
                  {data.items.map((r) => (
                    <tr key={`${r.emp_code}-${r.date}`} className="border-b border-line transition-colors last:border-0 hover:bg-slate-50">
                      <td className="px-3 py-2 font-semibold">{r.emp_code}</td>
                      <td className="px-3 py-2">{r.date}</td>
                      <td className="px-3 py-2"><StatusBadge status={r.status} />{r.history.length > 0 && <span className="ml-1.5 rounded bg-violet-100 px-1.5 py-0.5 text-[11px] font-semibold text-violet-800">Corrected</span>}</td>
                      <td className="px-3 py-2" title={r.punch_in ? new Date(r.punch_in).toISOString() : ""}>{fmtIST(r.punch_in)}</td>
                      <td className="px-3 py-2" title={r.punch_out ? new Date(r.punch_out).toISOString() : ""}>{fmtIST(r.punch_out)}</td>
                      <td className="px-3 py-2">{r.work_hours ?? "—"}</td>
                      <td className="px-3 py-2">{r.late_minutes > 0 ? <span className="font-semibold text-warn">{r.late_minutes}m</span> : "0"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <div className="mt-3 flex items-center justify-between text-sm">
              <p aria-live="polite">Page {data.page} of {Math.max(1, Math.ceil(data.total / data.page_size))} · {data.total} total</p>
              <div className="flex gap-2">
                <GhostButton disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</GhostButton>
                <GhostButton onClick={() => setPage((p) => p + 1)}>Next</GhostButton>
              </div>
            </div>
          </>
        )
      )}
    </section>
  );
}

/* ---------------- punch desk (POST punch-in/out) ---------------- */

type PunchResult = { ok: true; text: string } | { ok: false; text: string };

function PunchPage() {
  const [emp, setEmp] = useState("");
  const [status, setStatus] = useState("PRESENT");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PunchResult | null>(null);
  const [recent, setRecent] = useState<AttendancePage | null>(null);

  async function loadRecent(code: string) {
    if (!code) { setRecent(null); return; }
    try {
      setRecent(await apiFetch<AttendancePage>(`/attendance?emp_code=${encodeURIComponent(code)}&page_size=5`));
    } catch { setRecent(null); }
  }

  async function punch(kind: "in" | "out") {
    setBusy(true);
    setResult(null);
    try {
      const rec = await apiFetch<{ emp_code: string; punch_in: number | null; punch_out: number | null; date: string; status: string }>(
        kind === "in" ? "/attendance/punch-in" : "/attendance/punch-out",
        { method: "POST", body: JSON.stringify(kind === "in" ? { emp_code: emp, status } : { emp_code: emp }) },
      );
      const t = kind === "in" ? rec.punch_in : rec.punch_out;
      setResult({ ok: true, text: `${kind === "in" ? "Punch in" : "Punch out"} recorded at ${fmtIST(t)} IST · ${rec.emp_code}, ${rec.date} (${rec.status}).` });
      await loadRecent(emp);
    } catch (e) {
      setResult({ ok: false, text: e instanceof AppError ? `${e.kind === "business_rule" ? "Rejected" : "Failed"}: ${e.message}` : "Request failed." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Punch desk" className="max-w-3xl">
      <PageHeader title="Punch desk" desc="Records what the server returns — never the browser clock." />
      <div className="grid gap-4 md:grid-cols-5">
        <Card className="p-4 md:col-span-2">
          <Field label="Employee code" hint="Customer code, e.g. EMP0001">
            <input value={emp} onChange={(e) => { setEmp(e.target.value); setResult(null); void loadRecent(e.target.value); }} placeholder="EMP0001" className={inputCls} required />
          </Field>
          <div className="mt-3">
            <Field label="Status (punch-in only)">
              <select value={status} onChange={(e) => setStatus(e.target.value)} className={inputCls}>
                <option>PRESENT</option><option>WFH</option><option>ON_DUTY</option>
              </select>
            </Field>
          </div>
        </Card>
        <div className="md:col-span-3">
          <Card className="p-4">
            <div className="flex flex-col gap-2 sm:flex-row">
              <PrimaryButton onClick={() => void punch("in")} disabled={busy || !emp} className="flex-1 py-3">
                {busy ? "Working…" : `Punch in${emp ? `: ${emp}` : ""}`}
              </PrimaryButton>
              <PrimaryButton onClick={() => void punch("out")} disabled={busy || !emp} className="flex-1 py-3">
                {busy ? "Working…" : `Punch out${emp ? `: ${emp}` : ""}`}
              </PrimaryButton>
            </div>
            <p className="mt-2 text-xs text-slate-500">Both stay enabled — the backend judges validity (duplicate → 409, unknown → 404).</p>
            <div aria-live="polite" className="mt-3">
              {result && (
                <p className={`rounded-lg border p-3 text-sm ${result.ok ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-red-200 bg-red-50 text-red-900"}`}>
                  {result.text}
                </p>
              )}
            </div>
          </Card>
          {recent && recent.items.length > 0 && (
            <Card className="mt-4 overflow-hidden">
              <p className="border-b border-line px-4 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Recent for {emp}</p>
              {recent.items.map((r) => (
                <div key={r.date} className="flex items-center justify-between border-b border-line px-4 py-2 text-sm last:border-0">
                  <span>{r.date} · <StatusBadge status={r.status} /></span>
                  <span className="text-slate-500">{fmtIST(r.punch_in)} → {fmtIST(r.punch_out)}</span>
                </div>
              ))}
            </Card>
          )}
        </div>
      </div>
    </section>
  );
}

/* ---------------- app ---------------- */

export default function App() {
  return (
    <Router>
      <div className="min-h-screen">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:m-2 focus:rounded focus:bg-white focus:p-2">Skip to content</a>
        <div className="mx-auto flex max-w-6xl flex-col gap-6 p-4 md:flex-row md:p-6">
          <nav aria-label="Primary" className="shrink-0 md:w-52">
            <div className="mb-4 flex items-center gap-2">
              <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M4 5v14M9 5v14M14 5v14M4 15l16-6" stroke="#0f766e" strokeWidth="2.4" strokeLinecap="round" fill="none" />
              </svg>
              <span className="text-lg font-semibold tracking-tight">Muster</span>
              <span className="rounded-md bg-slate-200 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">Demo</span>
            </div>
            <ul className="flex gap-1 md:flex-col">
              {NAV.map((n) => (
                <li key={n.to}>
                  <NavLink to={n.to} end={n.end}
                    className={({ isActive }) => `block rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive ? "bg-brand text-white" : "text-slate-600 hover:bg-white hover:text-ink"}`}>
                    {n.label}
                  </NavLink>
                </li>
              ))}
            </ul>
            <p className="mt-4 hidden rounded-lg border border-line bg-white px-3 py-2 text-xs leading-relaxed text-slate-500 md:block">
              API: same-origin /api → :8000. Every figure is a server response.
            </p>
          </nav>
          <main id="main" className="min-w-0 flex-1">
            <Routes>
              <Route path="/" element={<OverviewPage />} />
              <Route path="/attendance" element={<RecordsPage />} />
              <Route path="/punch" element={<PunchPage />} />
              <Route path="*" element={<EmptyPanel text="Unknown page. Use the navigation." />} />
            </Routes>
          </main>
        </div>
      </div>
    </Router>
  );
}
