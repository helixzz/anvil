import ReactECharts from "echarts-for-react";
import type { PhaseSummary } from "@/api";
import { humanBps, humanBytes, humanIops } from "@/lib/format";

export type SweepAxis = "block_size" | "iodepth";
export type SweepMetric = "iops" | "bw" | "lat_mean" | "lat_p99";

interface Props {
  title: string;
  subtitle?: string;
  phases: PhaseSummary[];
  xAxis: SweepAxis;
  metric: SweepMetric;
  patternFilter?: (p: string) => boolean;
  height?: number;
}

function phaseValue(phase: PhaseSummary, metric: SweepMetric): number | null {
  switch (metric) {
    case "iops":
      return phase.read_iops ?? phase.write_iops ?? null;
    case "bw":
      return phase.read_bw_bytes ?? phase.write_bw_bytes ?? null;
    case "lat_mean":
      return phase.read_clat_mean_ns ?? phase.write_clat_mean_ns ?? null;
    case "lat_p99":
      return phase.read_clat_p99_ns ?? phase.write_clat_p99_ns ?? null;
  }
}

export function SweepChart({
  title,
  subtitle,
  phases,
  xAxis,
  metric,
  patternFilter,
  height = 280,
}: Props) {
  const filtered = phases.filter((p) => !patternFilter || patternFilter(p.pattern));
  const points: { x: number; y: number; name: string; pattern: string }[] = [];
  for (const p of filtered) {
    const y = phaseValue(p, metric);
    if (y == null) continue;
    points.push({
      x: xAxis === "block_size" ? p.block_size : p.iodepth,
      y,
      name: p.phase_name,
      pattern: p.pattern,
    });
  }
  points.sort((a, b) => a.x - b.x);

  const byPattern: Record<string, { x: number; y: number; name: string }[]> = {};
  for (const pt of points) {
    (byPattern[pt.pattern] = byPattern[pt.pattern] || []).push({
      x: pt.x,
      y: pt.y,
      name: pt.name,
    });
  }

  const metricFormatter: Record<SweepMetric, (v: number) => string> = {
    iops: humanIops,
    bw: humanBps,
    lat_mean: (v) => (v / 1000).toFixed(1) + " µs",
    lat_p99: (v) => (v / 1000).toFixed(1) + " µs",
  };
  const xFormatter =
    xAxis === "block_size"
      ? (v: number) => humanBytes(v)
      : (v: number) => `QD${v}`;

  const palette = ["#60a5fa", "#f4a340", "#4ade80", "#c084fc", "#f87171"];
  const series = Object.entries(byPattern).map(([pattern, pts], idx) => ({
    name: pattern,
    type: "line" as const,
    smooth: false,
    symbol: "circle",
    symbolSize: 8,
    lineStyle: { width: 2, color: palette[idx % palette.length] },
    itemStyle: { color: palette[idx % palette.length] },
    data: pts.map((p) => [p.x, p.y]),
  }));

  return (
    <div>
      {subtitle && (
        <div className="dim" style={{ fontSize: 11, marginLeft: 8, marginBottom: -4 }}>
          {subtitle}
        </div>
      )}
      <ReactECharts
        style={{ height, width: "100%" }}
        notMerge
        lazyUpdate
        option={{
          animation: false,
          textStyle: { fontFamily: "inherit" },
          grid: { top: 48, right: 20, bottom: 40, left: 70 },
          title: {
            text: title,
            left: 8,
            top: 4,
            textStyle: { color: "#e2e8f0", fontSize: 13, fontWeight: 500 },
          },
          tooltip: {
            trigger: "axis",
            backgroundColor: "#111a2e",
            borderColor: "#233256",
            textStyle: { color: "#e2e8f0" },
            formatter: (
              params: { seriesName: string; value: [number, number] }[],
            ) => {
              const x = params[0]?.value[0];
              const xs = xFormatter(x as number);
              const rows = params
                .map((p) => `${p.seriesName}: ${metricFormatter[metric](p.value[1])}`)
                .join("<br/>");
              return `${xs}<br/>${rows}`;
            },
          },
          legend: {
            data: series.map((s) => s.name),
            textStyle: { color: "#94a3b8" },
            top: 24,
            right: 10,
          },
          xAxis: {
            type: "log",
            logBase: 2,
            name: xAxis === "block_size" ? "Block size" : "Queue depth",
            nameTextStyle: { color: "#94a3b8" },
            axisLine: { lineStyle: { color: "#233256" } },
            axisLabel: { color: "#94a3b8", formatter: xFormatter },
          },
          yAxis: {
            type: "value",
            axisLine: { lineStyle: { color: "#233256" } },
            axisLabel: { color: "#94a3b8", formatter: metricFormatter[metric] },
            splitLine: { lineStyle: { color: "#1a2440" } },
          },
          series,
        }}
      />
    </div>
  );
}
