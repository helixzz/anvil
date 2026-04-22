import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import dayjs from "dayjs";
import ReactECharts from "echarts-for-react";

import { api } from "@/api";
import { humanBps, humanIops } from "@/lib/format";

export default function DeviceDetail() {
  const { t } = useTranslation();
  const { id = "" } = useParams();

  const historyQ = useQuery({
    queryKey: ["device-history", id],
    queryFn: () => api.getDeviceHistory(id),
    enabled: !!id,
  });

  const chartOption = useMemo(() => {
    const runs = historyQ.data?.runs ?? [];
    const completed = runs.filter((r) => r.status === "complete" && r.finished_at);
    if (completed.length === 0) return null;
    const labels = completed.map((r) =>
      r.finished_at ? dayjs(r.finished_at).format("MM-DD HH:mm") : r.id.slice(-6),
    );
    const readIops = completed.map((r) => r.best_read_iops ?? 0);
    const writeIops = completed.map((r) => r.best_write_iops ?? 0);
    const readBw = completed.map((r) => (r.best_read_bw_bytes ?? 0) / 1e6);
    const writeBw = completed.map((r) => (r.best_write_bw_bytes ?? 0) / 1e6);

    const hasWriteIops = writeIops.some((v) => v > 0);
    const hasReadBw = readBw.some((v) => v > 0);
    const hasWriteBw = writeBw.some((v) => v > 0);

    const markLines = (historyQ.data?.firmware_changes ?? []).map((fc) => {
      const ts = dayjs(fc.captured_at);
      const idx = completed.findIndex(
        (r) => r.finished_at && dayjs(r.finished_at).isAfter(ts),
      );
      return {
        xAxis: idx >= 0 ? idx : completed.length - 1,
        label: { formatter: `fw ${fc.firmware}`, color: "#94a3b8", fontSize: 10 },
        lineStyle: { color: "#f4a340", type: "dashed" as const },
      };
    });

    const series: unknown[] = [
      {
        name: t("runs.readIops"),
        type: "bar",
        data: readIops,
        itemStyle: { color: "#60a5fa" },
        markLine: markLines.length > 0 ? { silent: true, symbol: "none", data: markLines } : undefined,
      },
    ];
    if (hasWriteIops) {
      series.push({
        name: t("runs.writeIops"),
        type: "bar",
        data: writeIops,
        itemStyle: { color: "#f4a340" },
      });
    }
    if (hasReadBw) {
      series.push({
        name: `${t("runs.readBw")} (MB/s)`,
        type: "line",
        yAxisIndex: 1,
        data: readBw,
        lineStyle: { color: "#4ade80" },
        itemStyle: { color: "#4ade80" },
        smooth: true,
      });
    }
    if (hasWriteBw) {
      series.push({
        name: `${t("runs.writeBw")} (MB/s)`,
        type: "line",
        yAxisIndex: 1,
        data: writeBw,
        lineStyle: { color: "#c084fc" },
        itemStyle: { color: "#c084fc" },
        smooth: true,
      });
    }

    return {
      animation: false,
      textStyle: { fontFamily: "inherit" },
      grid: { top: 40, right: 70, bottom: 70, left: 80 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#111a2e",
        borderColor: "#233256",
        textStyle: { color: "#e2e8f0" },
      },
      legend: { textStyle: { color: "#94a3b8" }, top: 8 },
      xAxis: {
        type: "category",
        data: labels,
        axisLabel: { color: "#94a3b8", fontSize: 10 },
        axisLine: { lineStyle: { color: "#233256" } },
      },
      yAxis: [
        {
          type: "value",
          name: "IOPS",
          nameTextStyle: { color: "#94a3b8" },
          axisLine: { lineStyle: { color: "#233256" } },
          axisLabel: { color: "#94a3b8", formatter: humanIops },
          splitLine: { lineStyle: { color: "#1a2440" } },
        },
        {
          type: "value",
          name: "MB/s",
          nameTextStyle: { color: "#94a3b8" },
          axisLine: { lineStyle: { color: "#233256" } },
          axisLabel: { color: "#94a3b8" },
          splitLine: { show: false },
        },
      ],
      series,
    };
  }, [historyQ.data, t]);

  if (!historyQ.data) {
    return <div className="card dim">{t("common.loading")}</div>;
  }
  const h = historyQ.data;

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <div>
          <h2>
            <span className="mono">{h.model}</span>
          </h2>
          <div className="dim" style={{ fontSize: 12 }}>
            serial: <span className="mono">{h.serial}</span>
            {h.firmware && (
              <>
                {" · "}fw: <span className="mono">{h.firmware}</span>
              </>
            )}
          </div>
        </div>
        <Link to="/devices">← {t("common.back")}</Link>
      </div>

      <div className="card">
        <h3>{t("devices.history")}</h3>
        {chartOption ? (
          <ReactECharts style={{ height: 320 }} option={chartOption} notMerge lazyUpdate />
        ) : (
          <div className="dim">{t("devices.noHistory")}</div>
        )}
      </div>

      <div className="card">
        <h3>{t("runs.title")}</h3>
        {h.runs.length === 0 ? (
          <div className="dim">{t("runs.noRuns")}</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>{t("runs.profile")}</th>
                <th>{t("runs.status")}</th>
                <th>{t("devices.bestReadIops")}</th>
                <th>{t("devices.bestWriteIops")}</th>
                <th>{t("devices.bestReadBw")}</th>
                <th>{t("devices.bestWriteBw")}</th>
                <th>{t("runs.finishedAt")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {h.runs.map((r) => (
                <tr key={r.id}>
                  <td className="mono" style={{ fontSize: 11 }}>{r.id.slice(-12)}</td>
                  <td>{r.profile_name}</td>
                  <td>
                    <span
                      className={`badge badge-${
                        r.status === "complete"
                          ? "ok"
                          : r.status === "failed"
                            ? "err"
                            : r.status === "running"
                              ? "running"
                              : "queued"
                      }`}
                    >
                      {r.status}
                    </span>
                  </td>
                  <td>{humanIops(r.best_read_iops)}</td>
                  <td>{humanIops(r.best_write_iops)}</td>
                  <td>{humanBps(r.best_read_bw_bytes)}</td>
                  <td>{humanBps(r.best_write_bw_bytes)}</td>
                  <td className="dim">
                    {r.finished_at ? dayjs(r.finished_at).format("YYYY-MM-DD HH:mm") : "—"}
                  </td>
                  <td>
                    <Link to={`/runs/${r.id}`}>{t("runs.viewReport")} →</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
