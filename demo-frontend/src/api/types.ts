// Mirrors openapi.yaml schemas. Field names follow the contract, not UI taste.
export type Status = "PRESENT" | "ABSENT" | "LEAVE" | "WFH" | "ON_DUTY";

export interface HistoryChange {
  from: number | string | boolean | null;
  to: number | string | boolean | null;
}

export interface HistoryEntry {
  at: number;
  by: string;
  reason: string;
  changes: Record<string, HistoryChange>;
}

export interface AttendanceRecord {
  emp_code: string;
  date: string;
  status: Status;
  punch_in: number | null;
  punch_out: number | null;
  work_hours: number | null;
  late_minutes: number;
  overtime_minutes: number;
  half_day: boolean;
  history: HistoryEntry[];
}

export interface AttendancePage {
  items: AttendanceRecord[];
  total: number;
  page: number;
  page_size: number;
}
