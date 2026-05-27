import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import ReactECharts from "echarts-for-react";

import { api, getToken, type Device } from "@/api";
import { humanBps, humanIops, humanNs } from "@/lib/format";
import { MultiSelect, type MultiSelectOption } from "@/components/MultiSelect";

const PALETTE = ["#60a5fa", "#f4a340", "#4ade80", "#c084fc", "#f87171", "#22d3ee", "#facc15", "#a78bfa"];

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

function GroupChart({ group, series }: { group: string; series: Series[] }) {
  const { t } = useTranslation();
  const groupPoints = series.map((s) => ({
    ...s,
    points: s.points.filter((p) => p.group === group),
  })).filter((s) => s.points.length > 0);

  if (groupPoints.length === 0) return null;

  const firstPoints = groupPoints[0].points;
  const hasBS = new Set(firstPoints.map((p) => p.bs_label)).size > 1;
  const hasThreads = new Set(firstPoints.map((p) => p.threads)).size > 1;
  const hasQD = new Set(firstPoints.map((p) => p.qd)).size > 1;

  const xAxis = hasBS ? "bs_label" : hasThreads ? "threads" : hasQD ? "qd" : "raw_name";
  const xLabel = hasBS ? t("profileCompare.blockSize") : hasThreads ? t("profileCompare.threads") : hasQD ? t("profileCompare.queueDepth") : t("profileCompare.phase");

  const xValues = [...new Set(firstPoints.map((p) => String(p[xAxis as keyof Point])))];

  const hasRead = firstPoints.some((p) => p.read_iops && p.read_iops > 0);
  const hasWrite = firstPoints.some((p) => p.write_iops && p.write_iops > 0);

  const charts: { title: string; metric: string; formatter: (v: number) => string }[] = [];
  if (hasRead) charts.push({ title: t("profileCompare.readIops"), metric: "read_iops", formatter: humanIops });
  if (hasWrite) charts.push({ title: t("profileCompare.writeIops"), metric: "write_iops", formatter: humanIops });
  if (hasRead) charts.push({ title: t("profileCompare.readBw"), metric: "read_bw_bytes", formatter: humanBps });
  if (hasWrite) charts.push({ title: t("profileCompare.writeBw"), metric: "write_bw_bytes", formatter: humanBps });
  if (hasRead) charts.push({ title: t("profileCompare.readLatency"), metric: "read_clat_mean_ns", formatter: humanNs });

  const groupLabel = t(`profileCompare.${group}` as any, group);

  return (
    <div className="card">
      <h3>{groupLabel}</h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(450px, 1fr))", gap: 16 }}>
        {charts.map((chart) => (
          <LineChart
            key={chart.metric}
            title={chart.title}
            xLabel={xLabel}
            xValues={xValues}
            xKey={xAxis}
            metric={chart.metric}
            formatter={chart.formatter}
            series={groupPoints}
          />
        ))}
      </div>
    </div>
  );
}

function LineChart({
  title, xLabel, xValues, xKey, metric, formatter, series,
}: {
  title: string; xLabel: string; xValues: string[];
  xKey: string; metric: string; formatter: (v: number) => string;
  series: { model: string; brand: string; serial: string; points: Point[] }[];
}) {
  const option = {
    animation: false,
    title: { text: title, textStyle: { color: "var(--fg)", fontSize: 13 }, left: "center", top: 4 },
    tooltip: { trigger: "axis", backgroundColor: "#111a2e", borderColor: "#233256", textStyle: { color: "#e2e8f0" } },
    legend: { bottom: 0, textStyle: { color: "#94a3b8", fontSize: 10 }, type: "scroll" },
    grid: { top: 40, bottom: 50, left: 70, right: 20 },
    xAxis: { type: "category", data: xValues, name: xLabel, nameLocation: "center", nameGap: 30, axisLine: { lineStyle: { color: "#233256" } }, axisLabel: { color: "#94a3b8" } },
    yAxis: { type: "value", axisLine: { lineStyle: { color: "#233256" } }, axisLabel: { color: "#94a3b8", formatter: (v: number) => formatter(v) }, splitLine: { lineStyle: { color: "#1a2440" } } },
    series: series.map((s, i) => ({
      name: `${s.brand} ${s.model}`.trim(),
      type: "line",
      smooth: true,
      symbol: "circle",
      symbolSize: 5,
      lineStyle: { width: 2 },
      itemStyle: { color: PALETTE[i % PALETTE.length] },
      data: xValues.map((x) => {
        const pt = s.points.find((p) => String(p[xKey as keyof Point]) === x);
        return pt ? (pt as any)[metric] ?? null : null;
      }),
    })),
  };

  return <ReactECharts style={{ height: 280 }} option={option} notMerge />;
}
