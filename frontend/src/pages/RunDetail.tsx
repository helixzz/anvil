import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import ReactECharts from "echarts-for-react";
import dayjs from "dayjs";

import { api } from "@/api";
import { humanBps, humanIops, humanNs } from "@/lib/format";
import { useRunStream } from "@/hooks/useRunStream";

interface Sample {
  t: number;
  read_iops: number | null;
  write_iops: number | null;
  read_bw_bytes: number | null;
  write_bw_bytes: number | null;
  read_clat_mean_ns: number | null;
  write_clat_mean_ns: number | null;
  phase: string;
}

export default function RunDetail() {
  const { t } = useTranslation();
  const { id = "" } = useParams();
  const runQ = useQuery({
    queryKey: ["run", id],
    queryFn: () => api.getRun(id),
    refetchInterval: (q) =>
      q.state.data?.status === "complete" || q.state.data?.status === "failed" || q.state.data?.status === "aborted"
        ? false
        : 2000,
    enabled: !!id,
  });

  const { events, connected } = useRunStream(id || null);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [currentPhase, setCurrentPhase] = useState<string | null>(null);

  useEffect(() => {
    for (const ev of events) {
      if (ev.event === "phase_started") {
        setCurrentPhase(ev.payload.phase_name as string);
      } else if (ev.event === "phase_sample") {
        const p = ev.payload;
        setSamples((prev) =>
          [
            ...prev,
            {
              t: Date.now(),
              read_iops: typeof p.read_iops === "number" ? (p.read_iops as number) : null,
              write_iops: typeof p.write_iops === "number" ? (p.write_iops as number) : null,
              read_bw_bytes:
                typeof p.read_bw_bytes === "number" ? (p.read_bw_bytes as number) : null,
              write_bw_bytes:
                typeof p.write_bw_bytes === "number" ? (p.write_bw_bytes as number) : null,
              read_clat_mean_ns:
                typeof p.read_clat_mean_ns === "number"
                  ? (p.read_clat_mean_ns as number)
                  : null,
              write_clat_mean_ns:
                typeof p.write_clat_mean_ns === "number"
                  ? (p.write_clat_mean_ns as number)
                  : null,
              phase: (p.phase_name as string) || currentPhase || "",
            },
          ].slice(-600),
        );
      } else if (ev.event === "phase_complete" || ev.event === "run_complete") {
        void runQ.refetch();
      }
    }
    // We intentionally depend only on the latest event count, not the full array reference change,
    // so the samples list accumulates across renders.
  }, [events, currentPhase, runQ]);

  const run = runQ.data;

  const chartOption = useMemo(() => {
    const readIops = samples
      .filter((s) => s.read_iops != null)
      .map((s) => [s.t, s.read_iops as number]);
    const writeIops = samples
      .filter((s) => s.write_iops != null)
      .map((s) => [s.t, s.write_iops as number]);

    return {
      animation: false,
      textStyle: { fontFamily: "inherit" },
      grid: { top: 40, right: 40, bottom: 40, left: 80 },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v: number) => humanIops(v),
        backgroundColor: "#111a2e",
        borderColor: "#233256",
        textStyle: { color: "#e2e8f0" },
      },
      legend: {
        data: [t("runs.readIops"), t("runs.writeIops")],
        textStyle: { color: "#94a3b8" },
        top: 4,
      },
      xAxis: {
        type: "time",
        axisLine: { lineStyle: { color: "#233256" } },
        axisLabel: { color: "#94a3b8" },
      },
      yAxis: {
        type: "value",
        name: "IOPS",
        nameTextStyle: { color: "#94a3b8" },
        axisLine: { lineStyle: { color: "#233256" } },
        axisLabel: { color: "#94a3b8", formatter: (v: number) => humanIops(v) },
        splitLine: { lineStyle: { color: "#1a2440" } },
      },
      series: [
        {
          name: t("runs.readIops"),
          type: "line",
          showSymbol: false,
          smooth: false,
          lineStyle: { width: 2, color: "#60a5fa" },
          areaStyle: { opacity: 0.2, color: "#60a5fa" },
          data: readIops,
        },
        {
          name: t("runs.writeIops"),
          type: "line",
          showSymbol: false,
          smooth: false,
          lineStyle: { width: 2, color: "#f4a340" },
          areaStyle: { opacity: 0.2, color: "#f4a340" },
          data: writeIops,
        },
      ],
    };
  }, [samples, t]);

  if (!run) {
    return (
      <div className="card dim">{t("common.loading")}</div>
    );
  }

  const latestSample = samples[samples.length - 1];

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <div>
          <h2 style={{ marginBottom: 4 }}>
            {run.profile_name} · <span className="mono" style={{ fontSize: 14 }}>{run.id}</span>
          </h2>
          <div className="dim">
            {run.device_path_at_run} ·{" "}
            <span
              className={`badge badge-${
                run.status === "complete" ? "ok" : run.status === "failed" ? "err" : run.status === "running" ? "running" : "queued"
              }`}
            >
              {t(`status_labels.${run.status}` as const, run.status)}
            </span>
            {connected ? (
              <span className="badge badge-ok" style={{ marginLeft: 8 }}>WS</span>
            ) : (
              <span className="badge badge-queued" style={{ marginLeft: 8 }}>WS idle</span>
            )}
          </div>
        </div>
        <div className="dim" style={{ textAlign: "right" }}>
          <div>{t("runs.queuedAt")}: <span className="mono">{dayjs(run.queued_at).format("HH:mm:ss")}</span></div>
          {run.started_at && <div>{t("runs.startedAt")}: <span className="mono">{dayjs(run.started_at).format("HH:mm:ss")}</span></div>}
          {run.finished_at && <div>{t("runs.finishedAt")}: <span className="mono">{dayjs(run.finished_at).format("HH:mm:ss")}</span></div>}
        </div>
      </div>

      <div className="card">
        <h3>{t("runs.liveIops")}</h3>
        {samples.length === 0 ? (
          <div className="dim" style={{ padding: "40px 0", textAlign: "center" }}>
            {run.status === "complete" || run.status === "failed"
              ? t("runs.completed")
              : t("runs.waitingForRunner")}
          </div>
        ) : (
          <ReactECharts option={chartOption} style={{ height: 360 }} notMerge={true} lazyUpdate={true} />
        )}
      </div>

      {latestSample && (
        <div className="row">
          <div className="card stretch">
            <h3>{t("runs.readIops")}</h3>
            <div className="mono" style={{ fontSize: 20 }}>{humanIops(latestSample.read_iops)}</div>
          </div>
          <div className="card stretch">
            <h3>{t("runs.writeIops")}</h3>
            <div className="mono" style={{ fontSize: 20 }}>{humanIops(latestSample.write_iops)}</div>
          </div>
          <div className="card stretch">
            <h3>{t("runs.readBw")}</h3>
            <div className="mono" style={{ fontSize: 20 }}>{humanBps(latestSample.read_bw_bytes)}</div>
          </div>
          <div className="card stretch">
            <h3>{t("runs.writeBw")}</h3>
            <div className="mono" style={{ fontSize: 20 }}>{humanBps(latestSample.write_bw_bytes)}</div>
          </div>
          <div className="card stretch">
            <h3>{t("runs.meanLat")}</h3>
            <div className="mono" style={{ fontSize: 20 }}>
              {humanNs(
                latestSample.read_clat_mean_ns ?? latestSample.write_clat_mean_ns,
              )}
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <h3>{t("runs.phases")}</h3>
        {run.phases.length === 0 ? (
          <div className="dim">{t("runs.noPhases")}</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Name</th>
                <th>Pattern</th>
                <th>BS</th>
                <th>QD</th>
                <th>Jobs</th>
                <th>{t("runs.readIops")}</th>
                <th>{t("runs.readBw")}</th>
                <th>{t("runs.writeIops")}</th>
                <th>{t("runs.writeBw")}</th>
                <th>{t("runs.meanLat")}</th>
                <th>{t("runs.p99Lat")}</th>
                <th>{t("runs.p9999Lat")}</th>
              </tr>
            </thead>
            <tbody>
              {run.phases.map((p) => (
                <tr key={p.id}>
                  <td>{p.phase_order}</td>
                  <td className="mono">{p.phase_name}</td>
                  <td>{p.pattern}</td>
                  <td>{p.block_size}</td>
                  <td>{p.iodepth}</td>
                  <td>{p.numjobs}</td>
                  <td>{humanIops(p.read_iops)}</td>
                  <td>{humanBps(p.read_bw_bytes)}</td>
                  <td>{humanIops(p.write_iops)}</td>
                  <td>{humanBps(p.write_bw_bytes)}</td>
                  <td>{humanNs(p.read_clat_mean_ns ?? p.write_clat_mean_ns)}</td>
                  <td>{humanNs(p.read_clat_p99_ns ?? p.write_clat_p99_ns)}</td>
                  <td>{humanNs(p.read_clat_p9999_ns ?? p.write_clat_p9999_ns)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {run.error_message && (
        <div className="card" style={{ background: "#3b1820", border: "1px solid #7f1d1d" }}>
          <h3>{t("runs.errorMessage")}</h3>
          <pre className="mono" style={{ whiteSpace: "pre-wrap" }}>{run.error_message}</pre>
        </div>
      )}
    </div>
  );
}
