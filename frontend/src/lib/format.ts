export function humanBytes(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"];
  let v = value;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : v >= 10 ? 1 : 2)} ${units[i]}`;
}

export function humanBps(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const units = ["B/s", "KiB/s", "MiB/s", "GiB/s", "TiB/s"];
  let v = value;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : v >= 10 ? 1 : 2)} ${units[i]}`;
}

export function humanNs(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (value < 1_000) return `${value.toFixed(0)} ns`;
  if (value < 1_000_000) return `${(value / 1_000).toFixed(2)} µs`;
  if (value < 1_000_000_000) return `${(value / 1_000_000).toFixed(2)} ms`;
  return `${(value / 1_000_000_000).toFixed(2)} s`;
}

export function humanIops(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)} M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)} k`;
  return value.toFixed(0);
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}
