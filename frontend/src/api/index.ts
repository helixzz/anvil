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
  physical_location?: {
    chassis?: string;
    bay?: string;
    tray?: string;
    port?: string;
    notes?: string;
  } | null;
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
  smart_before?: Record<string, unknown> | null;
  smart_after?: Record<string, unknown> | null;
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

export interface MetricPoint {
  ts: string;
  metric_name: string;
  value: number;
}

export interface PhaseSummary {
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
  read_clat_p99_ns: number | null;
  read_clat_p9999_ns: number | null;
  write_iops: number | null;
  write_bw_bytes: number | null;
  write_clat_mean_ns: number | null;
  write_clat_p99_ns: number | null;
  write_clat_p9999_ns: number | null;
}

export interface ModelIndexEntry {
  slug: string;
  brand: string;
  model: string;
  protocol: string;
  form_factor: string | null;
  capacity_bytes_typical: number | null;
  device_count: number;
  run_count: number;
  firmwares: string[];
  last_run_at: string | null;
}

export interface ModelDetail {
  slug: string;
  brand: string;
  model: string;
  protocol: string;
  form_factor: string | null;
  capacity_bytes_typical: number | null;
  firmwares: string[];
  devices: {
    id: string;
    serial: string;
    firmware: string | null;
    first_seen: string;
    last_seen: string;
    is_testable: boolean;
  }[];
  runs: {
    id: string;
    device_id: string;
    profile_name: string;
    status: string;
    queued_at: string;
    started_at: string | null;
    finished_at: string | null;
  }[];
  profiles_used: Record<string, number>;
  headline_metrics: {
    per_phase: {
      phase_name: string;
      pattern: string;
      block_size: number;
      iodepth: number;
      best_iops: number | null;
      best_bw_bytes: number | null;
      sample_count: number;
    }[];
  };
  stability: {
    iops_score: number | null;
    iops_cv: number | null;
    iops_sample_count: number | null;
    temperature_score: number | null;
    temp_range_c: number | null;
    temp_sample_count: number | null;
  };
}

export interface PhaseCompareSample {
  run_id: string;
  device_id: string;
  finished_at: string | null;
  read_iops: number | null;
  read_bw_bytes: number | null;
  read_clat_mean_ns: number | null;
  read_clat_p99_ns: number | null;
  read_clat_p9999_ns: number | null;
  write_iops: number | null;
  write_bw_bytes: number | null;
  write_clat_mean_ns: number | null;
  write_clat_p99_ns: number | null;
}

export interface MetricSummary {
  mean: number;
  median: number;
  best: number;
  count: number;
}

export interface CrossModelCompareEntry {
  slug: string;
  brand: string | null;
  model: string | null;
  device_count?: number;
  samples: PhaseCompareSample[];
  summary: Partial<Record<
    | "read_iops"
    | "read_bw_bytes"
    | "write_iops"
    | "write_bw_bytes"
    | "read_clat_mean_ns"
    | "read_clat_p99_ns"
    | "write_clat_mean_ns"
    | "write_clat_p99_ns",
    MetricSummary | null
  >> & { sample_count: number };
}

export interface CrossModelCompareResult {
  phase_name: string;
  models: CrossModelCompareEntry[];
}

export interface PhaseHistogramDirection {
  total_ios: number;
  histogram: { bin_ns: number; count: number }[];
  cdf: { bin_ns: number; cdf: number; exceedance: number }[];
}
export interface PhaseHistogram {
  run_id: string;
  phase_id: string;
  phase_name: string;
  directions: Record<string, PhaseHistogramDirection>;
}

export interface DeviceHistoryEntry {
  id: string;
  profile_name: string;
  status: string;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  best_read_iops: number | null;
  best_write_iops: number | null;
  best_read_bw_bytes: number | null;
  best_write_bw_bytes: number | null;
  phase_count: number;
}
export interface DeviceHistory {
  device_id: string;
  model: string;
  serial: string;
  firmware: string | null;
  pcie?: Record<string, unknown> | null;
  runs: DeviceHistoryEntry[];
  firmware_changes: { captured_at: string; firmware: string }[];
}

export interface EnvironmentCheck {
  category: string;
  name: string;
  severity: string;
  value: string | null;
  status: string;
  expected: string | null;
  remediation: string | null;
  details: Record<string, unknown> | null;
}
export interface EnvironmentReport {
  summary: { total: number; pass: number; warn: number; fail: number; info: number };
  checks: EnvironmentCheck[];
}

export interface TunePreviewEntry {
  key: string;
  category?: string;
  path?: string;
  desired?: string;
  current?: string | null;
  will_change?: boolean;
  description?: string;
  error?: string;
}

export interface TuneResult {
  key: string;
  path: string;
  before: string | null;
  after: string | null;
  ok: boolean;
  error?: string | null;
}

export interface TuneReceipt {
  receipt_id?: string;
  results: TuneResult[];
  reverted: boolean;
  revert_error?: string | null;
}

export interface FleetStats {
  device_count: number;
  testable_device_count: number;
  distinct_models: number;
  distinct_brands: number;
  total_runs: number;
  complete_runs: number;
  failed_runs: number;
  aborted_runs: number;
  approx_bytes_written: number;
}

export interface LeaderboardEntry {
  run_id: string;
  device_id: string;
  brand: string;
  model: string;
  finished_at: string | null;
  value: number | null;
  read_iops: number | null;
  read_bw_bytes: number | null;
  read_clat_mean_ns: number | null;
  read_clat_p99_ns: number | null;
}
export interface LeaderboardCategory {
  title: string;
  metric: string;
  entries: LeaderboardEntry[];
}
export type Leaderboards = Record<string, LeaderboardCategory>;

export interface PcieDegradedEntry {
  device_id: string;
  brand: string;
  model: string;
  serial: string;
  capability: Record<string, unknown> | null;
  status: Record<string, unknown> | null;
  speed_degraded: boolean;
  width_degraded: boolean;
}

export interface ActivityDay {
  day: string;
  total: number;
  complete: number;
  failed: number;
  aborted: number;
}
export interface ActivityTimeline {
  days: number;
  series: ActivityDay[];
}

export interface AlarmEntry {
  run_id: string;
  device_id: string;
  model: string | null;
  profile: string;
  status: string;
  finished_at: string | null;
  error_message: string | null;
}

export interface SniaRoundCell {
  phase_id: string;
  phase_name: string;
  block_size_label: string;
  rwmix_write_pct: number;
  iodepth: number;
  numjobs: number;
  runtime_s: number;
  read_iops: number | null;
  write_iops: number | null;
  read_bw_bytes: number | null;
  write_bw_bytes: number | null;
  read_clat_p99_ns: number | null;
  write_clat_p99_ns: number | null;
}
export interface SniaAnalysis {
  run_id: string;
  profile: string;
  rounds: {
    round_idx: number;
    cells: SniaRoundCell[];
    canonical_4k_100w_iops: number | null;
  }[];
  steady_state: {
    steady: boolean;
    reason: string;
    rounds_observed: number;
    window: number[];
    window_mean: number | null;
    window_range: number | null;
    range_limit: number | null;
    range_ok: boolean;
    slope_per_round: number | null;
    slope_across_window: number | null;
    slope_limit: number | null;
    slope_ok: boolean;
  };
}

export interface AnvilUser {
  id: string;
  username: string;
  display_name: string | null;
  role: "viewer" | "operator" | "admin";
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface SsoConfig {
  enabled: boolean;
  idp_metadata_url: string;
  idp_entity_id: string;
  sp_entity_id: string;
  sp_acs_url: string;
  username_attribute: string;
  display_name_attribute: string;
  email_attribute: string;
  groups_attribute: string;
  default_role: string;
  mappings: { group: string; role: string }[];
  version?: string | null;
  expected_version?: string | null;
}

export const api = {
  status: () => jsonFetch<SystemStatus>("/api/status"),
  whoami: () =>
    jsonFetch<{ user_id: string | null; username: string; role: string; is_token: boolean }>(
      "/api/auth/me",
    ),
  login: (username: string, password: string) =>
    jsonFetch<{ token: string; user: AnvilUser }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  getSsoConfig: () => jsonFetch<SsoConfig>("/api/auth/sso/config"),
  ssoStatus: () =>
    jsonFetch<{ enabled: boolean; sp_entity_id: string; idp_entity_id: string }>(
      "/api/auth/sso/status",
    ),
  saveSsoConfig: (config: SsoConfig) =>
    jsonFetch<SsoConfig>("/api/auth/sso/config", {
      method: "PUT",
      body: JSON.stringify(config),
    }),
  ssoTestAssertion: (body: { username: string; display_name?: string | null; groups: string[] }) =>
    jsonFetch<{ token: string; user: AnvilUser }>("/api/auth/sso/assertion", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  adminListUsers: () => jsonFetch<AnvilUser[]>("/api/admin/users"),
  adminCreateUser: (body: { username: string; password: string; display_name?: string; role: string }) =>
    jsonFetch<AnvilUser>("/api/admin/users", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  adminUpdateUser: (
    id: string,
    body: { display_name?: string; role?: string; is_active?: boolean; new_password?: string },
  ) =>
    jsonFetch<AnvilUser>(`/api/admin/users/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  adminDeleteUser: (id: string) =>
    jsonFetch<{ deleted: string }>(`/api/admin/users/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  listDevices: () => jsonFetch<Device[]>("/api/devices"),
  getDevice: (id: string) => jsonFetch<Device>(`/api/devices/${encodeURIComponent(id)}`),
  rescanDevices: () => jsonFetch<Device[]>("/api/devices/rescan", { method: "POST" }),
  setDeviceLocation: (
    id: string,
    body: { chassis?: string | null; bay?: string | null; tray?: string | null; port?: string | null; notes?: string | null },
  ) =>
    jsonFetch<{ device_id: string; physical_location: Record<string, string> | null }>(
      `/api/devices/${encodeURIComponent(id)}/location`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),
  getDeviceHistory: (id: string) =>
    jsonFetch<DeviceHistory>(`/api/devices/${encodeURIComponent(id)}/history`),
  listRuns: () => jsonFetch<RunSummary[]>("/api/runs"),
  listProfiles: () => jsonFetch<Profile[]>("/api/runs/profiles"),
  getRun: (id: string) => jsonFetch<Run>(`/api/runs/${id}`),
  abortRun: (id: string) =>
    jsonFetch<{ run_id: string; result: string }>(`/api/runs/${id}/abort`, {
      method: "POST",
    }),
  getRunTimeseries: (id: string, metric?: string) => {
    const qs = metric ? `?metric=${encodeURIComponent(metric)}` : "";
    return jsonFetch<MetricPoint[]>(`/api/runs/${id}/timeseries${qs}`);
  },
  getRunPhases: (id: string) => jsonFetch<PhaseSummary[]>(`/api/runs/${id}/phases`),
  getPhaseHistogram: (runId: string, phaseId: string) =>
    jsonFetch<PhaseHistogram>(
      `/api/runs/${encodeURIComponent(runId)}/phases/${encodeURIComponent(phaseId)}/histogram`,
    ),
  getSniaAnalysis: (runId: string) =>
    jsonFetch<SniaAnalysis>(
      `/api/runs/${encodeURIComponent(runId)}/snia-analysis`,
    ),
  createRun: (body: {
    device_id: string;
    profile_name: string;
    confirm_serial_last6?: string;
  }) =>
    jsonFetch<Run>("/api/runs", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listModels: () => jsonFetch<ModelIndexEntry[]>("/api/models"),
  getModel: (slug: string) => jsonFetch<ModelDetail>(`/api/models/${encodeURIComponent(slug)}`),
  compareModelPhase: (slug: string, phase_name: string) =>
    jsonFetch<{ phase_name: string; samples: PhaseCompareSample[] }>(
      `/api/models/${encodeURIComponent(slug)}/compare?phase_name=${encodeURIComponent(phase_name)}`,
    ),
  commonPhasesAcrossModels: (slugs: string[]) =>
    jsonFetch<{ slugs: string[]; phase_names: string[] }>(
      `/api/models/compare/common-phases?slugs=${encodeURIComponent(slugs.join(","))}`,
    ),
  compareAcrossModels: (slugs: string[], phase_name: string) =>
    jsonFetch<CrossModelCompareResult>(
      `/api/models/compare?slugs=${encodeURIComponent(slugs.join(","))}&phase_name=${encodeURIComponent(phase_name)}`,
    ),
  getEnvironment: () => jsonFetch<EnvironmentReport>("/api/environment"),
  tunePreview: (keys?: string[]) => {
    const qs = keys && keys.length ? `?keys=${encodeURIComponent(keys.join(","))}` : "";
    return jsonFetch<{ preview: TunePreviewEntry[] }>(`/api/environment/tune/preview${qs}`);
  },
  tuneApply: (keys?: string[] | null) =>
    jsonFetch<TuneReceipt>(`/api/environment/tune/apply`, {
      method: "POST",
      body: JSON.stringify({ keys: keys ?? null }),
    }),
  tuneRevert: (receiptId: string) =>
    jsonFetch<TuneReceipt>(`/api/environment/tune/revert`, {
      method: "POST",
      body: JSON.stringify({ receipt_id: receiptId }),
    }),
  fleetStats: () => jsonFetch<FleetStats>("/api/dashboard/fleet-stats"),
  leaderboards: (limit = 5) =>
    jsonFetch<Leaderboards>(`/api/dashboard/leaderboards?limit=${limit}`),
  pcieDegraded: () => jsonFetch<PcieDegradedEntry[]>("/api/dashboard/pcie-degraded"),
  activity: (days = 30) =>
    jsonFetch<ActivityTimeline>(`/api/dashboard/activity?days=${days}`),
  alarms: (hours = 24) =>
    jsonFetch<AlarmEntry[]>(`/api/dashboard/alarms?hours=${hours}`),
  getRunShare: (id: string) =>
    jsonFetch<{ run_id: string; share_slug: string | null }>(
      `/api/runs/${encodeURIComponent(id)}/share`,
    ),
  createRunShare: (id: string) =>
    jsonFetch<{ run_id: string; share_slug: string }>(
      `/api/runs/${encodeURIComponent(id)}/share`,
      { method: "POST" },
    ),
  revokeRunShare: (id: string) =>
    jsonFetch<{ run_id: string; share_slug: null }>(
      `/api/runs/${encodeURIComponent(id)}/share`,
      { method: "DELETE" },
    ),
};

export function wsUrl(path: string): string {
  const base = apiBase();
  const u = new URL(path, base || window.location.origin);
  u.protocol = u.protocol.replace(/^http/, "ws");
  const token = getToken();
  if (token) u.searchParams.set("token", token);
  return u.toString();
}
