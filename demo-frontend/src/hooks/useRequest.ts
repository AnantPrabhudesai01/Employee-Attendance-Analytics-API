import { useCallback, useEffect, useState } from "react";

export type ReqStatus = "loading" | "success" | "error";

/** One request, previous data kept while refreshing. No global store in v1. */
export function useRequest<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [status, setStatus] = useState<ReqStatus>("loading");
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const refetch = useCallback(async () => {
    setIsRefreshing(true);
    try {
      setData(await fn());
      setStatus("success");
      setError(null);
    } catch (e) {
      setError(e as Error);
      setStatus("error");
    } finally {
      setIsRefreshing(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    setStatus("loading");
    void refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { status, data, error, isRefreshing, refetch };
}

export function fmtIST(ms: number | null): string {
  if (ms === null) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
  }).format(new Date(ms));
}
