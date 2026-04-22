const STORAGE_KEY = "anvil_bearer_token";

export function getToken(): string | null {
  return localStorage.getItem(STORAGE_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(STORAGE_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(STORAGE_KEY);
}

function apiBase(): string {
  return (
    (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_BASE ||
    ""
  );
}

async function jsonFetch<T>(
  input: string,
  init: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  headers.set("Content-Type", "application/json");
  const res = await fetch(`${apiBase()}${input}`, { ...init, headers });
  if (res.status === 401 || res.status === 403) {
    clearToken();
    window.dispatchEvent(new Event("anvil:auth-required"));
    throw new Error("Authentication required");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface Device {
  id: string;
  fingerprint: string;
  model: string;
  serial: string;
  firmware: string | null;
  vendor: string | null;
  brand: string | null;
  protocol: string;
  form_factor: string | null;
  capacity_bytes: number | null;
  sector_size_logical: number | null;
  sector_size_physical: number | null;
  wwid: string | null;
  current_device_path: string | null;
  is_testable: boolean;
  exclusion_reason: string | null;
  first_seen: string;
  last_seen: string;
  metadata_json: Record<string, unknown>;
}

export interface ProfilePhase {
  name: string;
  pattern: string;
  block_size: number;
  iodepth: number;
  numjobs: number;
  runtime_s: number;
  rwmix_write_pct: number;
  ramp_time_s: number;
  read_only: boolean;
}

export interface Profile {
  name: string;
  title: string;
  description: string;
  estimated_duration_seconds: number;
  destructive: boolean;
  phases: ProfilePhase[];
}

export interface RunPhase {
  id: string;
  phase_order: number;
  phase_name: string;
  pattern: string;
  block_size: number;
  iodepth: number;
  numjobs: number;
  rwmix_write_pct: number;
  runtime_s: number;
  started_at: string | null;
  finished_at: string | null;
  read_iops: number | null;
  read_bw_bytes: number | null;
  read_clat_mean_ns: number | null;
  read_clat_p50_ns: number | null;
  read_clat_p99_ns: number | null;
  read_clat_p999_ns: number | null;
  read_clat_p9999_ns: number | null;
  write_iops: number | null;
  write_bw_bytes: number | null;
  write_clat_mean_ns: number | null;
  write_clat_p50_ns: number | null;
  write_clat_p99_ns: number | null;
  write_clat_p999_ns: number | null;
  write_clat_p9999_ns: number | null;
}

export interface Run {
  id: string;
  device_id: string;
  profile_name: string;
  status: string;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  device_path_at_run: string;
  phases: RunPhase[];
  host_system?: Record<string, unknown> | null;
}

export interface RunSummary {
  id: string;
  device_id: string;
  device_model: string;
  device_serial: string;
  profile_name: string;
  status: string;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface SystemStatus {
  version: string;
  runner_connected: boolean;
  simulation_mode: boolean;
  device_count: number;
  running_count: number;
  queued_count: number;
  uptime_seconds: number;
}

export const api = {
  status: () => jsonFetch<SystemStatus>("/api/status"),
  listDevices: () => jsonFetch<Device[]>("/api/devices"),
  rescanDevices: () => jsonFetch<Device[]>("/api/devices/rescan", { method: "POST" }),
  listRuns: () => jsonFetch<RunSummary[]>("/api/runs"),
  listProfiles: () => jsonFetch<Profile[]>("/api/runs/profiles"),
  getRun: (id: string) => jsonFetch<Run>(`/api/runs/${id}`),
  createRun: (body: {
    device_id: string;
    profile_name: string;
    confirm_serial_last6?: string;
  }) =>
    jsonFetch<Run>("/api/runs", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export function wsUrl(path: string): string {
  const base = apiBase();
  const u = new URL(path, base || window.location.origin);
  u.protocol = u.protocol.replace(/^http/, "ws");
  const token = getToken();
  if (token) u.searchParams.set("token", token);
  return u.toString();
}
