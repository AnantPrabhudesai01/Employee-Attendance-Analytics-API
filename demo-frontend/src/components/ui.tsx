import type { ReactNode } from "react";

/* ---------- primitives: one look everywhere ---------- */

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-line bg-white ${className}`}>{children}</div>;
}

export function PageHeader({ title, desc, action }: { title: string; desc?: string; action?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {desc && <p className="mt-0.5 text-sm text-slate-500">{desc}</p>}
      </div>
      {action}
    </div>
  );
}

export function PrimaryButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50 ${props.className ?? ""}`}
    />
  );
}

export function GhostButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`rounded-lg border border-line bg-white px-3 py-2 text-sm transition-colors hover:bg-slate-50 disabled:opacity-50 ${props.className ?? ""}`}
    />
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block text-sm">
      <span className="font-medium">{label}</span>
      <span className="mt-1 block">{children}</span>
      {hint && <span className="mt-0.5 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

export const inputCls = "w-full rounded-lg border border-line bg-white px-2.5 py-2 text-[15px] outline-none focus:border-brand";

export function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "PRESENT" ? "border-emerald-200 bg-emerald-50 text-emerald-800"
    : status === "WFH" ? "border-sky-200 bg-sky-50 text-sky-800"
    : status === "ON_DUTY" ? "border-indigo-200 bg-indigo-50 text-indigo-800"
    : status === "LEAVE" ? "border-amber-200 bg-amber-50 text-amber-800"
    : "border-red-200 bg-red-50 text-red-800";
  return <span className={`inline-block rounded-md border px-2 py-0.5 text-xs font-semibold ${tone}`}>{status}</span>;
}

/* ---------- honest states (the meme's "skeleton loaders" critique, fixed) ---------- */

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div aria-label="Loading" className="overflow-hidden rounded-xl border border-line bg-white">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-3 border-b border-line px-3 py-3 last:border-0">
          <div className="h-4 w-20 animate-pulse rounded bg-slate-200" />
          <div className="h-4 w-24 animate-pulse rounded bg-slate-200" />
          <div className="h-4 w-16 animate-pulse rounded bg-slate-200" />
          <div className="hidden h-4 w-16 animate-pulse rounded bg-slate-200 sm:block" />
          <div className="hidden h-4 w-12 animate-pulse rounded bg-slate-200 md:block" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonKpis() {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="Loading">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="rounded-xl border border-line bg-white p-4">
          <div className="h-3 w-24 animate-pulse rounded bg-slate-200" />
          <div className="mt-2 h-8 w-16 animate-pulse rounded bg-slate-200" />
          <div className="mt-2 h-3 w-32 animate-pulse rounded bg-slate-100" />
        </div>
      ))}
    </div>
  );
}

export function ErrorPanel({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm">
      <p className="font-semibold text-red-900">{message}</p>
      <p className="mt-1 text-slate-600">
        The backend decides — check input or start the API, then{" "}
        <button onClick={onRetry} className="font-medium underline hover:text-red-900">retry</button>.
      </p>
    </div>
  );
}

export function EmptyPanel({ text }: { text: string }) {
  return <p className="rounded-xl border border-dashed border-line bg-white p-8 text-center text-sm text-slate-500">{text}</p>;
}

export function Metric({ label, value, context, to }: { label: string; value: string; context?: string; to?: string }) {
  const body = (
    <>
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-[28px] font-semibold leading-9 tracking-tight">{value}</p>
      {context && <p className="mt-1 text-xs text-slate-500">{context}</p>}
    </>
  );
  return (
    <div className="rounded-xl border border-line bg-white p-4">
      {to ? <a href={to} className="block hover:opacity-80">{body}</a> : body}
    </div>
  );
}
