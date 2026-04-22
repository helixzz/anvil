import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import dayjs from "dayjs";

import { api } from "@/api";
import { humanBps, humanIops, humanNs } from "@/lib/format";
import { useRunStream } from "@/hooks/useRunStream";
import {
  BW_FORMATTER,
  IOPS_FORMATTER,
  LAT_FORMATTER,
  TEMP_FORMATTER,
  TimeseriesChart,
} from "@/components/TimeseriesChart";
import { SweepChart } from "@/components/SweepChart";

const POLL_INTERVAL_MS = 2000;

function isTerminalStatus(status: string | undefined): boolean {
  return status === "complete" || status === "failed" || status === "aborted";
}

export default function RunDetail() {
  const { t } = useTranslation();
  const { id = "" } = useParams();

  const runQ = useQuery({
    queryKey: ["run", id],
    queryFn: () => api.getRun(id),
    refetchInterval: (q) =>
      isTerminalStatus(q.state.data?.status) ? false : POLL_INTERVAL_MS,
    enabled: !!id,
  });

  const phasesQ = useQuery({
    queryKey: ["run-phases", id],
    queryFn: () => api.getRunPhases(id),
    refetchInterval: (q) =>
      isTerminalStatus(runQ.data?.status)
        ? false
        : q.state.data && q.state.data.length > 0
          ? POLL_INTERVAL_MS * 2
          : POLL_INTERVAL_MS,
    enabled: !!id,
  });

  const timeseriesQ = useQuery({
    queryKey: ["run-timeseries", id],
    queryFn: () => api.getRunTimeseries(id),
    refetchInterval: (_q) =>
      isTerminalStatus(runQ.data?.status) ? false : POLL_INTERVAL_MS,
    enabled: !!id,
  });

  const { events, connected } = useRunStream(id || null);
  const [, setNudge] = useState(0);

  useEffect(() => {
    if (events.length === 0) return;
    const last = events[events.length - 1];
    if (
      last.event === "phase_sample" ||
      last.event === "smart_sample" ||
      last.event === "phase_complete" ||
      last.event === "run_complete"
    ) {
      setNudge((n) => n + 1);
      void timeseriesQ.refetch();
      if (last.event === "phase_complete" || last.event === "run_complete") {
        void runQ.refetch();
        void phasesQ.refetch();
      }
    }
  }, [events, runQ, phasesQ, timeseriesQ]);

  const run = runQ.data;
  const phases = phasesQ.data ?? [];
  const metrics = timeseriesQ.data ?? [];

  const latestSample = useMemo(() => {
    const readIops = [...metrics].reverse().find((m) => m.metric_name === "read_iops");
    const writeIops = [...metrics].reverse().find((m) => m.metric_name === "write_iops");
    const readBw = [...metrics].reverse().find((m) => m.metric_name === "read_bw_bytes");
    const writeBw = [...metrics].reverse().find((m) => m.metric_name === "write_bw_bytes");
    const readClat = [...metrics].reverse().find((m) => m.metric_name === "read_clat_mean_ns");
    const temp = [...metrics].reverse().find((m) => m.metric_name === "temperature_c");
    return {
      read_iops: readIops?.value,
      write_iops: writeIops?.value,
      read_bw_bytes: readBw?.value,
      write_bw_bytes: writeBw?.value,
      read_clat_mean_ns: readClat?.value,
      temperature_c: temp?.value,
    };
  }, [metrics]);

  const { bsSweepPhases, qdSweepPhases } = useMemo(() => {
    const bsGroupKey = (p: { pattern: string; iodepth: number; numjobs: number }) =>
      `${p.pattern}|${p.iodepth}|${p.numjobs}`;
    const qdGroupKey = (p: { pattern: string; block_size: number; numjobs: number }) =>
      `${p.pattern}|${p.block_size}|${p.numjobs}`;
    const bsBuckets: Record<string, typeof phases> = {};
    const qdBuckets: Record<string, typeof phases> = {};
    for (const p of phases) {
      (bsBuckets[bsGroupKey(p)] = bsBuckets[bsGroupKey(p)] || []).push(p);
      (qdBuckets[qdGroupKey(p)] = qdBuckets[qdGroupKey(p)] || []).push(p);
    }
    const bsSweep = Object.values(bsBuckets).flatMap((g) =>
      new Set(g.map((p) => p.block_size)).size >= 3 ? g : [],
    );
    const qdSweep = Object.values(qdBuckets).flatMap((g) =>
      new Set(g.map((p) => p.iodepth)).size >= 3 ? g : [],
    );
    return { bsSweepPhases: bsSweep, qdSweepPhases: qdSweep };
  }, [phases]);

  if (!run) {
    return <div className="card dim">{t("common.loading")}</div>;
  }

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <div>
          <h2 style={{ marginBottom: 4 }}>
            {run.profile_name} ·{" "}
            <span className="mono" style={{ fontSize: 14 }}>{run.id}</span>
          </h2>
          <div className="dim">
            {run.device_path_at_run} ·{" "}
            <span
              className={`badge badge-${
                run.status === "complete"
                  ? "ok"
                  : run.status === "failed"
                    ? "err"
                    : run.status === "running"
                      ? "running"
                      : "queued"
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
            {humanNs(latestSample.read_clat_mean_ns)}
          </div>
        </div>
        <div className="card stretch">
          <h3>{t("runs.temperature")}</h3>
          <div className="mono" style={{ fontSize: 20 }}>
            {latestSample.temperature_c != null
              ? `${latestSample.temperature_c.toFixed(1)} °C`
              : "—"}
          </div>
        </div>
      </div>

      <div className="card">
        <TimeseriesChart
          title={t("runs.liveIops")}
          metrics={metrics}
          phases={phases}
          yAxisName="IOPS"
          yAxisFormatter={IOPS_FORMATTER}
          tooltipFormatter={IOPS_FORMATTER}
          series={[
            { key: "read_iops", name: t("runs.readIops"), color: "#60a5fa", valueFormat: IOPS_FORMATTER },
            { key: "write_iops", name: t("runs.writeIops"), color: "#f4a340", valueFormat: IOPS_FORMATTER },
          ]}
        />
      </div>

      <div className="card">
        <TimeseriesChart
          title={t("runs.bandwidthOverTime")}
          metrics={metrics}
          phases={phases}
          yAxisName="B/s"
          yAxisFormatter={BW_FORMATTER}
          tooltipFormatter={BW_FORMATTER}
          series={[
            { key: "read_bw_bytes", name: t("runs.readBw"), color: "#60a5fa", valueFormat: BW_FORMATTER },
            { key: "write_bw_bytes", name: t("runs.writeBw"), color: "#f4a340", valueFormat: BW_FORMATTER },
          ]}
        />
      </div>

      <div className="card">
        <TimeseriesChart
          title={t("runs.latencyOverTime")}
          metrics={metrics}
          phases={phases}
          yAxisName="Latency"
          yAxisFormatter={LAT_FORMATTER}
          tooltipFormatter={LAT_FORMATTER}
          series={[
            { key: "read_clat_mean_ns", name: `${t("runs.readIops")} — ${t("runs.meanLat")}`, color: "#60a5fa", valueFormat: LAT_FORMATTER },
            { key: "write_clat_mean_ns", name: `${t("runs.writeIops")} — ${t("runs.meanLat")}`, color: "#f4a340", valueFormat: LAT_FORMATTER },
          ]}
        />
      </div>

      <div className="card">
        <TimeseriesChart
          title={t("runs.temperatureOverTime")}
          metrics={metrics}
          phases={phases}
          yAxisName="°C"
          yAxisFormatter={TEMP_FORMATTER}
          tooltipFormatter={TEMP_FORMATTER}
          series={[
            { key: "temperature_c", name: t("runs.temperature"), color: "#f87171", valueFormat: TEMP_FORMATTER },
          ]}
        />
      </div>

      {bsSweepPhases.length >= 3 && (
        <div className="card">
          <SweepChart
            title={t("runs.bsSweep")}
            subtitle="IOPS vs block size, grouped by read/write pattern"
            phases={bsSweepPhases}
            xAxis="block_size"
            metric="iops"
          />
        </div>
      )}
      {qdSweepPhases.length >= 3 && (
        <div className="card">
          <SweepChart
            title={t("runs.qdSweep")}
            subtitle="IOPS vs queue depth, grouped by read/write pattern"
            phases={qdSweepPhases}
            xAxis="iodepth"
            metric="iops"
          />
        </div>
      )}

      <div className="card">
        <h3>{t("runs.phases")}</h3>
        {phases.length === 0 ? (
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
              {phases.map((p) => (
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
