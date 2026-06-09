import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import ReactECharts from "echarts-for-react";

import { api, getToken, type Device } from "@/api";
import { humanBps, humanIops, humanNs } from "@/lib/format";
import { MultiSelect, type MultiSelectOption } from "@/components/MultiSelect";

const PALETTE = ["#60a5fa", "#f4a340", "#4ade80", "#c084fc", "#f87171", "#22d3ee", "#facc15", "#a78bfa"];
const HEATMAP_COLORS = ["#0c1426", "#1e3a5f", "#2563eb", "#3b82f6", "#60a5fa", "#fbbf24", "#f97316", "#ef4444"];

interface Point {
  raw_name: string;
  group: string;
  pattern: string;
  bs_label: string;
  bs_bytes: number;
  qd: number;
  threads: number;
  read_iops: number | null;
  write_iops: number | null;
  read_bw_bytes: number | null;
  write_bw_bytes: number | null;
  read_clat_mean_ns: number | null;
  write_clat_mean_ns: number | null;
}

interface Series {
  device_id: string;
  model: string;
  serial: string;
  brand: string;
  points: Point[];
}

interface CompareResult {
  profile_name: string;
  series: Series[];
  groups: string[];
}

type DimKey = "bs_label" | "qd" | "threads";

const BS_NUMERIC: Record<string, number> = {
  "512b": 0.5, "1k": 1, "2k": 2, "4k": 4, "8k": 8, "16k": 16,
  "32k": 32, "64k": 64, "128k": 128, "1m": 1024,
};

function sortDim(values: string[], key: DimKey): string[] {
  if (key === "bs_label") {
    return [...values].sort((a, b) => (BS_NUMERIC[a] ?? 0) - (BS_NUMERIC[b] ?? 0));
  }
  return [...values].sort((a, b) => Number(a) - Number(b));
}

export default function ProfileCompare() {
  const { t } = useTranslation();
  const devicesQ = useQuery({ queryKey: ["devices"], queryFn: api.listDevices });
  const profilesQ = useQuery({ queryKey: ["profiles"], queryFn: api.listProfiles });

  const [profileName, setProfileName] = useState("");
  const [deviceIds, setDeviceIds] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(false);

  const allDevices: Device[] = devicesQ.data ?? [];
  const profiles = profilesQ.data ?? [];

  const deviceOptions: MultiSelectOption[] = allDevices.map((d) => ({
    value: d.id,
    label: `${d.brand || ""} ${d.model}`.trim(),
    sub: d.serial,
  }));

  async function load() {
    if (!profileName || deviceIds.size < 2) return;
    setLoading(true);
    try {
      const resp = await fetch(
        `/api/profile-compare?profile_name=${encodeURIComponent(profileName)}&device_ids=${encodeURIComponent(Array.from(deviceIds).join(","))}`,
        { headers: { Authorization: `Bearer ${getToken() || ""}` } },
      );
      if (!resp.ok) throw new Error(await resp.text());
      setResult(await resp.json());
    } catch (e) {
      alert(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <div>
          <h2>{t("profileCompare.title")}</h2>
          <div className="dim" style={{ fontSize: 12 }}>
            {t("profileCompare.subtitle")}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="row" style={{ gap: 16, flexWrap: "wrap", alignItems: "end" }}>
          <div className="col" style={{ gap: 4, minWidth: 200 }}>
            <span className="dim" style={{ fontSize: 11 }}>{t("profileCompare.pickProfile")}</span>
            <select value={profileName} onChange={(e) => setProfileName(e.target.value)} style={{ fontSize: 13 }}>
              <option value="">—</option>
              {profiles.map((p) => (
                <option key={p.name} value={p.name}>{p.title} ({p.phases.length} phases)</option>
              ))}
            </select>
          </div>
          <div className="col" style={{ gap: 4, minWidth: 300 }}>
            <span className="dim" style={{ fontSize: 11 }}>{t("profileCompare.pickDevices")}</span>
            <MultiSelect
              options={deviceOptions}
              selected={deviceIds}
              onChange={setDeviceIds}
              placeholder={t("profileCompare.pickDevices")}
            />
          </div>
          <button className="btn-primary" onClick={load} disabled={loading || !profileName || deviceIds.size < 2}>
            {loading ? t("profileCompare.loading") : t("profileCompare.compare")}
          </button>
        </div>
      </div>

      {result && result.series.length > 0 && (
        <div className="col" style={{ gap: 24 }}>
          {result.groups.map((group) => (
            <GroupChart key={group} group={group} series={result.series} />
          ))}
        </div>
      )}

      {result && result.series.length === 0 && (
        <div className="card dim" style={{ textAlign: "center", padding: 40 }}>
          {t("profileCompare.noData")}
        </div>
      )}
    </div>
  );
}

function dimLabel(t: (k: string) => string, k: DimKey): string {
  if (k === "bs_label") return t("profileCompare.blockSize");
  if (k === "threads") return t("profileCompare.threads");
  return t("profileCompare.queueDepth");
}

function formatGroupLabel(group: string, t: (k: string, fallback?: string) => string): string {
  if (/^g[0-9]+$/.test(group)) return t(`profileCompare.${group}` as any, group);
  const m = group.match(/^sr_([0-9]+[kKmM]?b?)_(read|write|mixed)$/i);
  if (m) {
    const bs = m[1].toUpperCase();
    const pat = m[2].toLowerCase();
    const patLabel = pat === "read"
      ? t("profileCompare.patternRead", "Sequential Read")
      : pat === "write"
        ? t("profileCompare.patternWrite", "Sequential Write")
        : t("profileCompare.patternMixed", "Mixed");
    return `${bs} ${patLabel}`;
  }
  return group.split("_").map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join(" ");
}

function GroupChart({ group, series }: { group: string; series: Series[] }) {
  const { t } = useTranslation();
  const groupSeries = series
    .map((s) => ({ ...s, points: s.points.filter((p) => p.group === group) }))
    .filter((s) => s.points.length > 0);

  if (groupSeries.length === 0) return null;

  const allPoints = groupSeries.flatMap((s) => s.points);
  const bsValues = sortDim([...new Set(allPoints.map((p) => p.bs_label))], "bs_label");
  const qdValues = sortDim([...new Set(allPoints.map((p) => String(p.qd)))], "qd");
  const threadValues = sortDim([...new Set(allPoints.map((p) => String(p.threads)))], "threads");

  const dims: { key: DimKey; values: string[] }[] = [];
  if (bsValues.length > 1) dims.push({ key: "bs_label", values: bsValues });
  if (qdValues.length > 1) dims.push({ key: "qd", values: qdValues });
  if (threadValues.length > 1) dims.push({ key: "threads", values: threadValues });

  if (dims.length === 0) return null;

  const isMatrix = dims.length >= 2;
  const xDim = dims[0];
  const yDim = dims[1];

  const hasRead = allPoints.some((p) => p.read_iops && p.read_iops > 0);
  const hasWrite = allPoints.some((p) => p.write_iops && p.write_iops > 0);

  const charts: { title: string; metric: string; formatter: (v: number) => string }[] = [];
  if (hasRead) charts.push({ title: t("profileCompare.readIops"), metric: "read_iops", formatter: humanIops });
  if (hasWrite) charts.push({ title: t("profileCompare.writeIops"), metric: "write_iops", formatter: humanIops });
  if (hasRead) charts.push({ title: t("profileCompare.readBw"), metric: "read_bw_bytes", formatter: humanBps });
  if (hasWrite) charts.push({ title: t("profileCompare.writeBw"), metric: "write_bw_bytes", formatter: humanBps });
  if (hasRead) charts.push({ title: t("profileCompare.readLatency"), metric: "read_clat_mean_ns", formatter: humanNs });

  const groupLabel = formatGroupLabel(group, t as any);

  return (
    <div className="card">
      <h3>{groupLabel}</h3>
      <div className="col" style={{ gap: 24 }}>
        {charts.map((chart) =>
          isMatrix ? (
            <HeatmapRow
              key={chart.metric}
              title={chart.title}
              xDim={xDim}
              yDim={yDim}
              metric={chart.metric}
              formatter={chart.formatter}
              series={groupSeries}
              t={t as any}
            />
          ) : (
            <Chart2D
              key={chart.metric}
              title={chart.title}
              xDim={xDim}
              metric={chart.metric}
              formatter={chart.formatter}
              series={groupSeries}
              t={t as any}
            />
          ),
        )}
      </div>
    </div>
  );
}

function HeatmapRow({
  title, xDim, yDim, metric, formatter, series, t,
}: {
  title: string;
  xDim: { key: DimKey; values: string[] };
  yDim: { key: DimKey; values: string[] };
  metric: string;
  formatter: (v: number) => string;
  series: { device_id: string; model: string; brand: string; serial: string; points: Point[] }[];
  t: (k: string) => string;
}) {
  const allValues: number[] = [];
  series.forEach((dev) => {
    dev.points.forEach((p) => {
      const v = (p as any)[metric];
      if (typeof v === "number" && v > 0) allValues.push(v);
    });
  });
  const minVal = allValues.length ? Math.min(...allValues) : 0;
  const maxVal = allValues.length ? Math.max(...allValues) : 1;

  return (
    <div className="col" style={{ gap: 8 }}>
      <div style={{ fontSize: 13, fontWeight: 500, color: "var(--fg)" }}>{title}</div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${Math.min(series.length, 3)}, minmax(0, 1fr))`,
          gap: 12,
        }}
      >
        {series.map((dev, devIdx) => (
          <DeviceHeatmap
            key={dev.device_id}
            device={dev}
            devColor={PALETTE[devIdx % PALETTE.length]}
            xDim={xDim}
            yDim={yDim}
            metric={metric}
            formatter={formatter}
            min={minVal}
            max={maxVal}
            t={t}
            title={title}
          />
        ))}
      </div>
    </div>
  );
}

function DeviceHeatmap({
  device, devColor, xDim, yDim, metric, formatter, min, max, t, title,
}: {
  device: { model: string; brand: string; serial: string; points: Point[] };
  devColor: string;
  xDim: { key: DimKey; values: string[] };
  yDim: { key: DimKey; values: string[] };
  metric: string;
  formatter: (v: number) => string;
  min: number;
  max: number;
  t: (k: string) => string;
  title: string;
}) {
  const devLabel = `${device.brand} ${device.model}`.trim() || device.serial;

  const data: [number, number, number | "-"][] = [];
  xDim.values.forEach((xv, xi) => {
    yDim.values.forEach((yv, yi) => {
      const pt = device.points.find(
        (p) =>
          String(p[xDim.key as keyof Point]) === xv &&
          String(p[yDim.key as keyof Point]) === yv,
      );
      const val = pt ? (pt as any)[metric] : null;
      data.push([xi, yi, typeof val === "number" && val > 0 ? val : "-"]);
    });
  });

  const option = {
    animation: false,
    title: {
      text: devLabel,
      textStyle: { color: devColor, fontSize: 12, fontWeight: 500 },
      left: "center",
      top: 4,
    },
    tooltip: {
      position: "top",
      backgroundColor: "#111a2e",
      borderColor: "#233256",
      textStyle: { color: "#e2e8f0", fontSize: 11 },
      formatter: (p: any) => {
        const xv = xDim.values[p.value[0]];
        const yv = yDim.values[p.value[1]];
        const v = p.value[2];
        return `<b>${devLabel}</b><br/>${dimLabel(t, xDim.key)}: ${xv}<br/>${dimLabel(t, yDim.key)}: ${yv}<br/>${title}: ${v === "-" ? "—" : formatter(v)}`;
      },
    },
    grid: { top: 36, bottom: 64, left: 64, right: 16 },
    xAxis: {
      type: "category",
      data: xDim.values,
      name: dimLabel(t, xDim.key),
      nameLocation: "middle",
      nameGap: 28,
      nameTextStyle: { color: "#cbd5e1", fontSize: 11, fontWeight: 500 },
      axisLine: { lineStyle: { color: "#233256" } },
      axisLabel: { color: "#94a3b8", fontSize: 10 },
      splitArea: { show: false },
    },
    yAxis: {
      type: "category",
      data: yDim.values,
      name: dimLabel(t, yDim.key),
      nameLocation: "middle",
      nameGap: 40,
      nameRotate: 90,
      nameTextStyle: { color: "#cbd5e1", fontSize: 11, fontWeight: 500 },
      axisLine: { lineStyle: { color: "#233256" } },
      axisLabel: { color: "#94a3b8", fontSize: 10 },
      splitArea: { show: false },
    },
    visualMap: {
      min: min,
      max: max,
      calculable: false,
      orient: "horizontal",
      left: "center",
      bottom: 4,
      itemWidth: 12,
      itemHeight: 80,
      textStyle: { color: "#94a3b8", fontSize: 9 },
      formatter: (v: number) => formatter(v),
      inRange: { color: HEATMAP_COLORS },
    },
    series: [
      {
        name: devLabel,
        type: "heatmap",
        data,
        label: {
          show: true,
          fontSize: 9,
          color: "#fff",
          formatter: (p: any) => (p.value[2] === "-" ? "" : compactFormat(p.value[2], metric)),
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 8,
            shadowColor: "rgba(0,0,0,0.5)",
            borderColor: "#fff",
            borderWidth: 1,
          },
        },
      },
    ],
  };

  return <ReactECharts style={{ height: 320, minWidth: 0 }} option={option} notMerge />;
}

function compactFormat(v: number, metric: string): string {
  if (metric.includes("iops")) {
    if (v >= 1000) return `${(v / 1000).toFixed(0)}k`;
    return v.toFixed(0);
  }
  if (metric.includes("bw")) {
    const mb = v / (1024 * 1024);
    if (mb >= 1024) return `${(mb / 1024).toFixed(1)}G`;
    return `${mb.toFixed(0)}M`;
  }
  if (metric.includes("latency") || metric.includes("clat")) {
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}ms`;
    if (v >= 1000) return `${(v / 1000).toFixed(0)}μs`;
    return `${v.toFixed(0)}ns`;
  }
  return String(v);
}

function Chart2D({
  title, xDim, metric, formatter, series, t,
}: {
  title: string;
  xDim: { key: DimKey; values: string[] };
  metric: string;
  formatter: (v: number) => string;
  series: { model: string; brand: string; serial: string; points: Point[] }[];
  t: (k: string) => string;
}) {
  const echartsSeries = series.map((dev, devIdx) => {
    const devLabel = `${dev.brand} ${dev.model}`.trim() || dev.serial;
    const data = xDim.values.map((xv) => {
      const pt = dev.points.find((p) => String(p[xDim.key as keyof Point]) === xv);
      return pt ? (pt as any)[metric] ?? null : null;
    });
    return {
      name: devLabel,
      type: "line",
      smooth: false,
      symbol: "circle",
      symbolSize: 5,
      lineStyle: { width: 2 },
      itemStyle: { color: PALETTE[devIdx % PALETTE.length] },
      data,
    };
  });

  const option = {
    animation: false,
    title: { text: title, textStyle: { color: "var(--fg)", fontSize: 13 }, left: "center", top: 4 },
    tooltip: {
      trigger: "axis" as const,
      backgroundColor: "#111a2e",
      borderColor: "#233256",
      textStyle: { color: "#e2e8f0", fontSize: 11 },
      valueFormatter: (v: number | null) => (v == null ? "—" : formatter(v)),
    },
    legend: { bottom: 0, textStyle: { color: "#94a3b8", fontSize: 10 }, type: "scroll" },
    grid: { top: 50, bottom: 60, left: 80, right: 24 },
    xAxis: {
      type: "category" as const,
      data: xDim.values,
      name: dimLabel(t, xDim.key),
      nameLocation: "middle" as const,
      nameGap: 30,
      nameTextStyle: { color: "#cbd5e1", fontSize: 12, fontWeight: 500 },
      axisLine: { lineStyle: { color: "#233256" } },
      axisLabel: { color: "#94a3b8", fontSize: 11 },
    },
    yAxis: {
      type: "value" as const,
      name: title,
      nameLocation: "middle" as const,
      nameGap: 60,
      nameRotate: 90,
      nameTextStyle: { color: "#cbd5e1", fontSize: 12, fontWeight: 500 },
      axisLine: { lineStyle: { color: "#233256" } },
      axisLabel: { color: "#94a3b8", formatter: (v: number) => formatter(v), fontSize: 11 },
      splitLine: { lineStyle: { color: "#1a2440" } },
    },
    series: echartsSeries,
  };

  return <ReactECharts style={{ height: 300 }} option={option} notMerge />;
}
