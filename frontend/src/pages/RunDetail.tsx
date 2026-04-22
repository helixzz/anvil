import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import dayjs from "dayjs";

import { api, getToken } from "@/api";
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
import { LatencyHistogramChart } from "@/components/LatencyHistogramChart";
import { SniaAnalysisCard } from "@/components/SniaAnalysisCard";
import { PcieLinkCard, type PcieLinkData } from "@/components/PcieLinkCard";

const POLL_INTERVAL_MS = 2000;

function isTerminalStatus(status: string | undefined): boolean {
  return status === "complete" || status === "failed" || status === "aborted";
}

function numericSmartFields(
  smart: Record<string, unknown> | null | undefined,
): Record<string, number> {
  const out: Record<string, number> = {};
  if (!smart) return out;
  const nvme = (smart as Record<string, unknown>).nvme_smart_log;
  if (nvme && typeof nvme === "object") {
    for (const [k, v] of Object.entries(nvme as Record<string, unknown>)) {
      if (typeof v === "number") out[k] = v;
    }
  }
  return out;
}

function SmartDiffCard({
  smartBefore,
  smartAfter,
}: {
  smartBefore: Record<string, unknown> | null | undefined;
  smartAfter: Record<string, unknown> | null | undefined;
}) {
  const { t } = useTranslation();
  const before = numericSmartFields(smartBefore);
  const after = numericSmartFields(smartAfter);
  const keys = Array.from(new Set([...Object.keys(before), ...Object.keys(after)])).sort();
  const rows = keys
    .map((k) => ({ k, b: before[k], a: after[k], delta: (after[k] ?? 0) - (before[k] ?? 0) }))
    .filter((r) => r.b !== undefined || r.a !== undefined);

  if (rows.length === 0) return null;

  const TEMP_KEY = "temperature";

  return (
    <div className="card">
      <h3>{t("runs.smartDiff")}</h3>
      <div className="dim" style={{ fontSize: 11, marginBottom: 8 }}>
        {t("runs.smartDiffHelp")}
      </div>
      <table>
        <thead>
          <tr>
            <th>{t("runs.smartField")}</th>
            <th>{t("runs.smartBefore")}</th>
            <th>{t("runs.smartAfter")}</th>
            <th>{t("runs.smartDelta")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.k}>
              <td className="mono" style={{ fontSize: 12 }}>{r.k}</td>
              <td className="mono">
                {r.b === undefined ? "—" : r.k === TEMP_KEY ? `${r.b - 273} °C` : r.b.toLocaleString()}
              </td>
              <td className="mono">
                {r.a === undefined ? "—" : r.k === TEMP_KEY ? `${r.a - 273} °C` : r.a.toLocaleString()}
              </td>
              <td
                className="mono"
                style={{
                  color: r.delta === 0 ? "#94a3b8" : r.delta > 0 ? "#fde68a" : "#a7f3d0",
                }}
              >
                {r.b === undefined || r.a === undefined
                  ? "—"
                  : (r.delta > 0 ? "+" : "") + r.delta.toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function RunDetail() {
  const { t } = useTranslation();
  const { id = "" } = useParams();
  const queryClient = useQueryClient();

  const runQ = useQuery({
    queryKey: ["run", id],
    queryFn: () => api.getRun(id),
    refetchInterval: (q) =>
      isTerminalStatus(q.state.data?.status) ? false : POLL_INTERVAL_MS,
    enabled: !!id,
  });

  const terminal = isTerminalStatus(runQ.data?.status);

  const phasesQ = useQuery({
    queryKey: ["run-phases", id],
    queryFn: () => api.getRunPhases(id),
    refetchInterval: terminal ? false : POLL_INTERVAL_MS,
    enabled: !!id,
  });

  const timeseriesQ = useQuery({
    queryKey: ["run-timeseries", id],
    queryFn: () => api.getRunTimeseries(id),
    refetchInterval: terminal ? false : POLL_INTERVAL_MS,
    enabled: !!id,
  });

  const { events, connected } = useRunStream(id || null);

  // Fast-path nudge: when WS delivers a phase_complete / run_complete event,
  // invalidate the polling queries immediately so the next poll happens now
  // rather than waiting the full POLL_INTERVAL_MS. Depend only on the events
  // array length; do NOT depend on query objects (their identity changes on
  // every render and would trigger an infinite refetch loop).
  const lastProcessedIdx = useRef(0);
  useEffect(() => {
    for (let i = lastProcessedIdx.current; i < events.length; i++) {
      const ev = events[i];
      if (ev.event === "phase_complete" || ev.event === "run_complete") {
        void queryClient.invalidateQueries({ queryKey: ["run", id] });
        void queryClient.invalidateQueries({ queryKey: ["run-phases", id] });
      }
    }
    lastProcessedIdx.current = events.length;
  }, [events.length, id, queryClient]);

  const run = runQ.data;
  const phases = phasesQ.data ?? [];
  const metrics = timeseriesQ.data ?? [];

  const abortMut = useMutation({
    mutationFn: () => api.abortRun(id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["run", id] }),
  });

  const [histogramPhaseId, setHistogramPhaseId] = useState<string>("");
  const [histogramMode, setHistogramMode] = useState<"pdf" | "cdf" | "exceedance">("exceedance");

  const histogramQ = useQuery({
    queryKey: ["phase-histogram", id, histogramPhaseId],
    queryFn: () => api.getPhaseHistogram(id, histogramPhaseId),
    enabled: !!id && !!histogramPhaseId,
  });

  useEffect(() => {
    if (histogramPhaseId) return;
    const firstComplete = phases.find((p) => p.finished_at);
    if (firstComplete) setHistogramPhaseId(firstComplete.id);
  }, [phases, histogramPhaseId]);

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
          {!terminal && (
            <div style={{ marginTop: 8 }}>
              <button
                className="btn-danger"
                disabled={abortMut.isPending}
                onClick={() => {
                  if (window.confirm(t("runs.abortConfirm"))) abortMut.mutate();
                }}
              >
                {abortMut.isPending ? t("common.loading") : t("runs.abortBtn")}
              </button>
            </div>
          )}
          <div style={{ marginTop: 8, display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <a
              href={`/api/runs/${encodeURIComponent(run.id)}/export.html?token=${encodeURIComponent(getToken() ?? "")}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              <button>{t("runs.exportHtml")}</button>
            </a>
            <a
              href={`/api/runs/${encodeURIComponent(run.id)}/export.json?token=${encodeURIComponent(getToken() ?? "")}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              <button>{t("runs.exportJson")}</button>
            </a>
          </div>
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
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>{t("runs.latencyDistribution")}</h3>
          <div className="row" style={{ gap: 8 }}>
            <select
              value={histogramPhaseId}
              onChange={(e) => setHistogramPhaseId(e.target.value)}
            >
              <option value="">—</option>
              {phases
                .filter((p) => p.finished_at)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.phase_name}
                  </option>
                ))}
            </select>
            <select
              value={histogramMode}
              onChange={(e) => setHistogramMode(e.target.value as "pdf" | "cdf" | "exceedance")}
            >
              <option value="pdf">{t("runs.pdf")}</option>
              <option value="cdf">{t("runs.cdf")}</option>
              <option value="exceedance">{t("runs.exceedance")}</option>
            </select>
          </div>
        </div>
        {!histogramPhaseId ? (
          <div className="dim" style={{ padding: 20, textAlign: "center" }}>
            {t("runs.histogramEmpty")}
          </div>
        ) : histogramQ.isLoading ? (
          <div className="dim">{t("common.loading")}</div>
        ) : histogramQ.data && Object.keys(histogramQ.data.directions).length > 0 ? (
          <LatencyHistogramChart
            title={`${histogramQ.data.phase_name} · ${histogramMode.toUpperCase()}`}
            directions={histogramQ.data.directions}
            mode={histogramMode}
          />
        ) : (
          <div className="dim" style={{ padding: 20, textAlign: "center" }}>
            {t("runs.histogramUnavailable")}
          </div>
        )}
      </div>

      {(run.smart_before || run.smart_after) && (
        <SmartDiffCard smartBefore={run.smart_before} smartAfter={run.smart_after} />
      )}

      {(run.host_system as { pcie_at_run?: PcieLinkData } | undefined)?.pcie_at_run && (
        <PcieLinkCard
          pcie={(run.host_system as { pcie_at_run: PcieLinkData }).pcie_at_run}
        />
      )}

      {run.profile_name.startsWith("snia_") && <SniaAnalysisCard runId={run.id} />}

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
