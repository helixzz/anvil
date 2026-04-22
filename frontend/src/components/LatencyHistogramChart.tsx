import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { humanNs } from "@/lib/format";

export interface HistBin {
  bin_ns: number;
  count: number;
}
export interface CdfPoint {
  bin_ns: number;
  cdf: number;
  exceedance: number;
}
export interface HistogramDirection {
  total_ios: number;
  histogram: HistBin[];
  cdf: CdfPoint[];
}

interface Props {
  title: string;
  directions: Record<string, HistogramDirection>;
  mode: "pdf" | "cdf" | "exceedance";
  height?: number;
}

const DIRECTION_COLOR: Record<string, string> = {
  read: "#60a5fa",
  write: "#f4a340",
};

export function LatencyHistogramChart({
  title,
  directions,
  mode,
  height = 300,
}: Props) {
  const series = useMemo(() => {
    const arr: unknown[] = [];
    for (const [direction, data] of Object.entries(directions)) {
      if (!data.total_ios) continue;
      const color = DIRECTION_COLOR[direction] || "#94a3b8";
      if (mode === "pdf") {
        const total = data.total_ios;
        const points = data.histogram.map((b) => [b.bin_ns, b.count / total]);
        arr.push({
          name: `${direction} · PDF`,
          type: "line",
          showSymbol: false,
          smooth: false,
          sampling: "lttb",
          lineStyle: { color, width: 2 },
          areaStyle: { color, opacity: 0.15 },
          data: points,
        });
      } else {
        const metric = mode === "cdf" ? "cdf" : "exceedance";
        const points = data.cdf.map((p) => [p.bin_ns, p[metric]]);
        arr.push({
          name: `${direction} · ${mode.toUpperCase()}`,
          type: "line",
          showSymbol: false,
          smooth: false,
          sampling: "lttb",
          lineStyle: { color, width: 2 },
          data: points,
        });
      }
    }
    return arr;
  }, [directions, mode]);

  const yAxis =
    mode === "pdf"
      ? {
          type: "value" as const,
          name: "probability",
          nameTextStyle: { color: "#94a3b8" },
          axisLine: { lineStyle: { color: "#233256" } },
          axisLabel: {
            color: "#94a3b8",
            formatter: (v: number) => v.toExponential(1),
          },
          splitLine: { lineStyle: { color: "#1a2440" } },
        }
      : {
          type: mode === "exceedance" ? ("log" as const) : ("value" as const),
          name: mode === "cdf" ? "P(latency ≤ x)" : "P(latency > x)",
          nameTextStyle: { color: "#94a3b8" },
          min: mode === "exceedance" ? 1e-6 : 0,
          max: 1,
          axisLine: { lineStyle: { color: "#233256" } },
          axisLabel: {
            color: "#94a3b8",
            formatter: (v: number) =>
              mode === "exceedance" ? v.toExponential(0) : v.toFixed(2),
          },
          splitLine: { lineStyle: { color: "#1a2440" } },
        };

  return (
    <ReactECharts
      style={{ height, width: "100%" }}
      notMerge
      lazyUpdate
      option={{
        animation: false,
        textStyle: { fontFamily: "inherit" },
        grid: { top: 48, right: 24, bottom: 40, left: 80 },
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
          valueFormatter: (v: number) =>
            mode === "pdf" ? v.toExponential(3) : v.toFixed(6),
        },
        legend: {
          data: series.map(
            (s) => (s as { name: string }).name,
          ),
          textStyle: { color: "#94a3b8" },
          top: 24,
        },
        xAxis: {
          type: "log",
          logBase: 10,
          name: "latency",
          nameTextStyle: { color: "#94a3b8" },
          axisLine: { lineStyle: { color: "#233256" } },
          axisLabel: {
            color: "#94a3b8",
            formatter: (v: number) => humanNs(v),
          },
        },
        yAxis,
        series,
      }}
    />
  );
}
