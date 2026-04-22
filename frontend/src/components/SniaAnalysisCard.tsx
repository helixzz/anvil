import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import ReactECharts from "echarts-for-react";
import { api } from "@/api";
import { humanIops } from "@/lib/format";

export function SniaAnalysisCard({ runId }: { runId: string }) {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ["snia-analysis", runId],
    queryFn: () => api.getSniaAnalysis(runId),
    enabled: !!runId,
  });

  const chartOption = useMemo(() => {
    const d = q.data;
    if (!d || d.rounds.length === 0) return null;
    const xs = d.rounds.map((r) => r.round_idx);
    const ys = d.rounds.map((r) => r.canonical_4k_100w_iops ?? 0);
    const ss = d.steady_state;
    const bandSeries: unknown[] = [];
    if (ss.window_mean != null && ss.range_limit != null) {
      const lower = ss.window_mean - ss.range_limit / 2;
      const upper = ss.window_mean + ss.range_limit / 2;
      bandSeries.push(
        {
          name: `${t("runs.sniaRangeBand")} (±20%)`,
          type: "line",
          data: xs.map(() => upper),
          lineStyle: { color: "#4ade80", type: "dashed", width: 1 },
          symbol: "none",
        },
        {
          name: `${t("runs.sniaRangeBand")} (-)`,
          type: "line",
          data: xs.map(() => lower),
          lineStyle: { color: "#4ade80", type: "dashed", width: 1 },
          symbol: "none",
          legendHoverLink: false,
          tooltip: { show: false },
          showInLegend: false,
        },
      );
    }
    return {
      animation: false,
      textStyle: { fontFamily: "inherit" },
      grid: { top: 50, right: 30, bottom: 50, left: 90 },
      title: {
        text: t("runs.sniaIopsPerRound"),
        left: 8,
        top: 4,
        textStyle: { color: "#e2e8f0", fontSize: 13, fontWeight: 500 },
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#111a2e",
        borderColor: "#233256",
        textStyle: { color: "#e2e8f0" },
        valueFormatter: (v: number) => humanIops(v),
      },
      legend: { textStyle: { color: "#94a3b8" }, top: 24 },
      xAxis: {
        type: "category",
        data: xs.map((x) => `R${x}`),
        axisLine: { lineStyle: { color: "#233256" } },
        axisLabel: { color: "#94a3b8" },
      },
      yAxis: {
        type: "value",
        name: "4K 100%w IOPS",
        nameTextStyle: { color: "#94a3b8" },
        axisLine: { lineStyle: { color: "#233256" } },
        axisLabel: { color: "#94a3b8", formatter: humanIops },
        splitLine: { lineStyle: { color: "#1a2440" } },
      },
      series: [
        {
          name: t("runs.sniaMetric"),
          type: "line",
          data: ys,
          symbol: "circle",
          symbolSize: 10,
          lineStyle: { color: "#f4a340", width: 2 },
          itemStyle: { color: "#f4a340" },
        },
        ...bandSeries,
      ],
    };
  }, [q.data, t]);

  if (!q.data) return null;
  if (q.data.rounds.length === 0) return null;
  const ss = q.data.steady_state;
  const badgeClass = ss.steady ? "badge-ok" : "badge-warn";

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <h3 style={{ margin: 0 }}>{t("runs.sniaAnalysis")}</h3>
        <span className={`badge ${badgeClass}`}>
          {ss.steady ? t("runs.sniaSteady") : ss.reason}
        </span>
      </div>
      <div className="dim" style={{ fontSize: 11, marginTop: 6 }}>
        {t("runs.sniaHelp")}
      </div>
      {chartOption && (
        <ReactECharts style={{ height: 260 }} option={chartOption} notMerge lazyUpdate />
      )}
      <table style={{ marginTop: 12 }}>
        <thead>
          <tr>
            <th>{t("runs.sniaCriterion")}</th>
            <th>{t("runs.sniaObserved")}</th>
            <th>{t("runs.sniaLimit")}</th>
            <th>{t("runs.status")}</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td className="mono">range (max − min)</td>
            <td className="mono">{ss.window_range?.toFixed(2) ?? "—"}</td>
            <td className="mono">{ss.range_limit?.toFixed(2) ?? "—"}</td>
            <td>
              <span className={`badge ${ss.range_ok ? "badge-ok" : "badge-err"}`}>
                {ss.range_ok ? "pass" : "fail"}
              </span>
            </td>
          </tr>
          <tr>
            <td className="mono">slope drift across window</td>
            <td className="mono">{ss.slope_across_window?.toFixed(2) ?? "—"}</td>
            <td className="mono">{ss.slope_limit?.toFixed(2) ?? "—"}</td>
            <td>
              <span className={`badge ${ss.slope_ok ? "badge-ok" : "badge-err"}`}>
                {ss.slope_ok ? "pass" : "fail"}
              </span>
            </td>
          </tr>
          <tr>
            <td className="mono dim">window mean</td>
            <td className="mono">{ss.window_mean?.toFixed(0) ?? "—"}</td>
            <td className="mono dim">—</td>
            <td className="dim">{ss.rounds_observed} rounds</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
