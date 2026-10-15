import { useState } from "react";
import { apiFetch, AppError } from "./api/client";
import type { AttendancePage } from "./api/types";
import { fmtIST, useRequest } from "./hooks/useRequest";

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "PRESENT" ? "bg-emerald-50 text-emerald-800 border-emerald-200"
    : status === "WFH" ? "bg-sky-50 text-sky-800 border-sky-200"
    : status === "ON_DUTY" ? "bg-indigo-50 text-indigo-800 border-indigo-200"
    : status === "LEAVE" ? "bg-amber-50 text-amber-800 border-amber-200"
    : "bg-red-50 text-red-800 border-red-200";
  return <span className={`inline-block rounded-md border px-2 py-0.5 text-xs font-medium ${tone}`}>{status}</span>;
}

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
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Attendance records</h1>
          <p className="text-sm text-slate-500">
            {data ? `Total ${data.total} (server count)` : "Filters map 1:1 to GET /attendance."}
          </p>
        </div>
        <button onClick={() => void refetch()} className="rounded-lg border border-line bg-white px-3 py-2 text-sm hover:bg-slate-50" disabled={isRefreshing}>
          {isRefreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <form
        className="mb-4 grid grid-cols-2 gap-3 rounded-xl border border-line bg-white p-4 md:grid-cols-5"
        onSubmit={(e) => { e.preventDefault(); setPage(1); void refetch(); }}
      >
        <label className="text-sm">Employee<input value={emp} onChange={(e) => setEmp(e.target.value)} placeholder="EMP0001" className="mt-1 w-full rounded-lg border border-line px-2 py-2" /></label>
        <label className="text-sm">From<input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="mt-1 w-full rounded-lg border border-line px-2 py-2" /></label>
        <label className="text-sm">To<input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="mt-1 w-full rounded-lg border border-line px-2 py-2" /></label>
        <label className="text-sm">Status
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="mt-1 w-full rounded-lg border border-line px-2 py-2">
            <option value="">All</option><option>PRESENT</option><option>WFH</option><option>ON_DUTY</option><option>ABSENT</option><option>LEAVE</option>
          </select>
        </label>
        <div className="flex items-end gap-2">
          <button type="submit" className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-700">Apply</button>
          <button type="button" onClick={() => { setEmp(""); setFrom(""); setTo(""); setStatus(""); setPage(1); }} className="rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100">Reset</button>
        </div>
      </form>

      {st === "loading" && <p className="rounded-xl border border-line bg-white p-8 text-center text-sm text-slate-500">Loading records…</p>}
      {st === "error" && (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm">
          <p className="font-medium">{error instanceof AppError ? error.message : "Request failed."}</p>
          <p className="mt-1 text-slate-600">Backend is the authority — fix input or start the API, then <button onClick={() => void refetch()} className="underline">retry</button>.</p>
        </div>
      )}
      {st === "success" && data && (
        data.items.length === 0 ? (
          <p className="rounded-xl border border-line bg-white p-8 text-center text-sm text-slate-500">No records for these filters.</p>
        ) : (
          <>
            <div className="overflow-x-auto rounded-xl border border-line bg-white">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-line text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-3 py-2">Employee</th><th className="px-3 py-2">Date</th><th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">In</th><th className="px-3 py-2">Out</th><th className="px-3 py-2">Work h</th><th className="px-3 py-2">Late</th>
                </tr></thead>
                <tbody>
                  {data.items.map((r) => (
                    <tr key={`${r.emp_code}-${r.date}`} className="border-b border-line last:border-0">
                      <td className="px-3 py-2 font-medium">{r.emp_code}</td>
                      <td className="px-3 py-2">{r.date}</td>
                      <td className="px-3 py-2"><StatusBadge status={r.status} />{r.history.length > 0 && <span className="ml-1 text-xs text-violet-700">Corrected</span>}</td>
                      <td className="px-3 py-2">{fmtIST(r.punch_in)}</td>
                      <td className="px-3 py-2">{fmtIST(r.punch_out)}</td>
                      <td className="px-3 py-2">{r.work_hours ?? "—"}</td>
                      <td className="px-3 py-2">{r.late_minutes}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex items-center justify-between text-sm">
              <p>Page {data.page} of {Math.max(1, Math.ceil(data.total / data.page_size))} · {data.total} total</p>
              <div className="flex gap-2">
                <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg border border-line bg-white px-3 py-1.5 disabled:opacity-40">Previous</button>
                <button onClick={() => setPage((p) => p + 1)} className="rounded-lg border border-line bg-white px-3 py-1.5">Next</button>
              </div>
            </div>
          </>
        )
      )}
    </section>
  );
}

export default function App() {
  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only">Skip to content</a>
      <div className="mx-auto flex max-w-6xl gap-6 p-6">
        <nav aria-label="Primary" className="w-52 shrink-0">
          <div className="mb-6 flex items-center gap-2">
            <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5v14M9 5v14M14 5v14M4 15l16-6" stroke="#0f766e" strokeWidth="2.4" strokeLinecap="round" /></svg>
            <span className="text-lg font-semibold">Muster</span>
            <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[11px] text-slate-600">Demo</span>
          </div>
          <p className="rounded-lg border border-line bg-white px-3 py-2 text-xs text-slate-500">API: same-origin /api → :8000</p>
        </nav>
        <main id="main" className="min-w-0 flex-1"><RecordsPage /></main>
      </div>
    </div>
  );
}
