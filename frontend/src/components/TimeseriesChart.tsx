import ReactECharts from "echarts-for-react";
import type { MetricPoint, PhaseSummary } from "@/api";
import { humanBps, humanIops, humanNs } from "@/lib/format";

interface SeriesDef {
  key: string;
  name: string;
  color: string;
  valueFormat: (v: number) => string;
}

interface Props {
  title: string;
  metrics: MetricPoint[];
  series: SeriesDef[];
  phases?: PhaseSummary[];
  height?: number;
  yAxisName?: string;
  yAxisFormatter?: (v: number) => string;
  tooltipFormatter?: (v: number) => string;
}

function phaseBoundaries(phases: PhaseSummary[] | undefined): { x: number; name: string }[] {
  if (!phases) return [];
  const out: { x: number; name: string }[] = [];
  for (const p of phases) {
    if (p.started_at) {
      out.push({ x: new Date(p.started_at).getTime(), name: p.phase_name });
    }
  }
  return out;
}

export function TimeseriesChart({
  title,
  metrics,
  series,
  phases,
  height = 280,
  yAxisName,
  yAxisFormatter,
  tooltipFormatter,
}: Props) {
  const grouped: Record<string, [number, number][]> = {};
  for (const s of series) grouped[s.key] = [];
  for (const m of metrics) {
    if (grouped[m.metric_name]) {
      grouped[m.metric_name].push([new Date(m.ts).getTime(), m.value]);
    }
  }
  for (const key of Object.keys(grouped)) {
    grouped[key].sort((a, b) => a[0] - b[0]);
  }

  const totalPoints = Object.values(grouped).reduce(
    (acc, arr) => acc + arr.length,
    0,
  );

  if (totalPoints === 0) {
    return (
      <div style={{ height }}>
        <div
          style={{
            fontSize: 13,
            fontWeight: 500,
            color: "#e2e8f0",
            marginBottom: 6,
          }}
        >
          {title}
        </div>
        <div
          style={{
            height: height - 24,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#94a3b8",
            border: "1px dashed #233256",
            borderRadius: 8,
            fontSize: 12,
          }}
        >
          {metrics.length === 0
            ? "Waiting for samples…"
            : `Received ${metrics.length} sample(s), none matched series keys`}
        </div>
      </div>
    );
  }

  const markLines = phaseBoundaries(phases).map((b, idx) => ({
    xAxis: b.x,
    label: {
      formatter: b.name,
      color: "#94a3b8",
      fontSize: 10,
      position: idx % 2 === 0 ? ("insideEndTop" as const) : ("insideEndBottom" as const),
    },
    lineStyle: { color: "#334155", type: "dashed" as const },
  }));

  return (
    <ReactECharts
      style={{ height, width: "100%" }}
      notMerge
      lazyUpdate
      option={{
        animation: false,
        textStyle: { fontFamily: "inherit" },
        grid: { top: 44, right: 24, bottom: 40, left: 70 },
        title: {
          text: `${title}  ·  ${totalPoints} pts`,
          left: 8,
          top: 4,
          textStyle: { color: "#e2e8f0", fontSize: 13, fontWeight: 500 },
        },
        tooltip: {
          trigger: "axis",
          backgroundColor: "#111a2e",
          borderColor: "#233256",
          textStyle: { color: "#e2e8f0" },
          valueFormatter: tooltipFormatter ?? ((v: number) => v.toFixed(2)),
        },
        legend: {
          data: series.map((s) => s.name),
          textStyle: { color: "#94a3b8" },
          top: 24,
          right: 10,
        },
        xAxis: {
          type: "time",
          axisLine: { lineStyle: { color: "#233256" } },
          axisLabel: { color: "#94a3b8" },
        },
        yAxis: {
          type: "value",
          name: yAxisName,
          nameTextStyle: { color: "#94a3b8" },
          axisLine: { lineStyle: { color: "#233256" } },
          axisLabel: {
            color: "#94a3b8",
            formatter: yAxisFormatter ?? ((v: number) => v.toString()),
          },
          splitLine: { lineStyle: { color: "#1a2440" } },
        },
        series: series.map((s) => ({
          name: s.name,
          type: "line",
          showSymbol: false,
          smooth: false,
          connectNulls: false,
          lineStyle: { width: 2, color: s.color },
          areaStyle: { opacity: 0.15, color: s.color },
          data: grouped[s.key],
          markLine:
            markLines.length > 0
              ? {
                  silent: true,
                  symbol: "none",
                  data: markLines,
                }
              : undefined,
        })),
      }}
    />
  );
}

export const IOPS_FORMATTER = (v: number) => humanIops(v);
export const BW_FORMATTER = (v: number) => humanBps(v);
export const LAT_FORMATTER = (v: number) => humanNs(v);
export const TEMP_FORMATTER = (v: number) => `${v.toFixed(1)} °C`;
