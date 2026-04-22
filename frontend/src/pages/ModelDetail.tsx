import { useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import dayjs from "dayjs";
import ReactECharts from "echarts-for-react";

import { api } from "@/api";
import { humanBps, humanBytes, humanIops } from "@/lib/format";

function fmtScore(score: number | null | undefined): { text: string; badge: string } {
  if (score == null) return { text: "—", badge: "badge" };
  const rounded = Math.round(score);
  let badge = "badge-err";
  if (rounded >= 80) badge = "badge-ok";
  else if (rounded >= 50) badge = "badge-warn";
  return { text: `${rounded} / 100`, badge: `badge ${badge}` };
}

export default function ModelDetail() {
  const { t } = useTranslation();
  const { slug = "" } = useParams();

  const modelQ = useQuery({
    queryKey: ["model", slug],
    queryFn: () => api.getModel(slug),
    enabled: !!slug,
  });

  const phases = modelQ.data?.headline_metrics.per_phase ?? [];
  const [selectedPhase, setSelectedPhase] = useState<string>("");

  const compareQ = useQuery({
    queryKey: ["model-compare", slug, selectedPhase],
    queryFn: () => api.compareModelPhase(slug, selectedPhase),
    enabled: !!slug && !!selectedPhase,
  });

  const compareOption = useMemo(() => {
    if (!compareQ.data) return null;
    const s = compareQ.data.samples;
    if (s.length === 0) return null;

    const labels = s.map((x, idx) => {
      const date = x.finished_at ? dayjs(x.finished_at).format("MM-DD HH:mm") : `#${idx + 1}`;
      return `${date}\n${x.device_id.slice(-6)}`;
    });
    const readIops = s.map((x) => x.read_iops ?? 0);
    const writeIops = s.map((x) => x.write_iops ?? 0);
    const readBw = s.map((x) => (x.read_bw_bytes ?? 0) / 1e6);
    const writeBw = s.map((x) => (x.write_bw_bytes ?? 0) / 1e6);

    const hasReadIops = readIops.some((v) => v > 0);
    const hasWriteIops = writeIops.some((v) => v > 0);
    const hasReadBw = readBw.some((v) => v > 0);
    const hasWriteBw = writeBw.some((v) => v > 0);

    const series: unknown[] = [];
    if (hasReadIops) {
      series.push({ name: t("runs.readIops"), type: "bar", data: readIops, itemStyle: { color: "#60a5fa" } });
    }
    if (hasWriteIops) {
      series.push({ name: t("runs.writeIops"), type: "bar", data: writeIops, itemStyle: { color: "#f4a340" } });
    }
    if (hasReadBw) {
      series.push({
        name: `${t("runs.readBw")} (MB/s)`,
        type: "line",
        yAxisIndex: 1,
        data: readBw,
        lineStyle: { color: "#4ade80" },
        itemStyle: { color: "#4ade80" },
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
        axisLabel: { color: "#94a3b8", interval: 0, fontSize: 10 },
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
  }, [compareQ.data, t]);

  if (!modelQ.data) {
    return <div className="card dim">{t("common.loading")}</div>;
  }
  const m = modelQ.data;
  const iopsScore = fmtScore(m.stability.iops_score);
  const tempScore = fmtScore(m.stability.temperature_score);

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <div>
          <h2>
            <span className="badge">{m.brand}</span>&nbsp;
            <span className="mono">{m.model}</span>
          </h2>
          <div className="dim">
            {m.protocol} ·{" "}
            {m.capacity_bytes_typical ? humanBytes(m.capacity_bytes_typical) : "—"}
            {m.firmwares.length > 0 && (
              <>
                &nbsp;·&nbsp;FW: <span className="mono">{m.firmwares.join(", ")}</span>
              </>
            )}
          </div>
        </div>
        <Link to="/models">← {t("common.back")}</Link>
      </div>

      <div className="row">
        <div className="card stretch">
          <h3>{t("models.deviceCount")}</h3>
          <div className="mono" style={{ fontSize: 20 }}>{m.devices.length}</div>
        </div>
        <div className="card stretch">
          <h3>{t("models.runCount")}</h3>
          <div className="mono" style={{ fontSize: 20 }}>{m.runs.length}</div>
        </div>
        <div className="card stretch">
          <h3>{t("models.iopsScore")}</h3>
          <div>
            <span className={iopsScore.badge}>{iopsScore.text}</span>
          </div>
          {m.stability.iops_cv != null && (
            <div className="dim" style={{ fontSize: 11, marginTop: 4 }}>
              {t("models.iopsCv")}:&nbsp;
              <span className="mono">{(m.stability.iops_cv * 100).toFixed(2)}%</span>
              &nbsp;· n={m.stability.iops_sample_count}
            </div>
          )}
        </div>
        <div className="card stretch">
          <h3>{t("models.temperatureScore")}</h3>
          <div>
            <span className={tempScore.badge}>{tempScore.text}</span>
          </div>
          {m.stability.temp_range_c != null && (
            <div className="dim" style={{ fontSize: 11, marginTop: 4 }}>
              {t("models.tempRange")}:&nbsp;
              <span className="mono">{m.stability.temp_range_c.toFixed(1)} °C</span>
              &nbsp;· n={m.stability.temp_sample_count}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <h3>{t("models.headlineMetrics")}</h3>
        {phases.length === 0 ? (
          <div className="dim">{t("models.noRuns")}</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Phase</th>
                <th>Pattern</th>
                <th>BS</th>
                <th>QD</th>
                <th>{t("models.bestIops")}</th>
                <th>{t("models.bestBw")}</th>
                <th>{t("models.samples")}</th>
              </tr>
            </thead>
            <tbody>
              {phases.map((p) => (
                <tr key={p.phase_name}>
                  <td className="mono">{p.phase_name}</td>
                  <td>{p.pattern}</td>
                  <td>{humanBytes(p.block_size)}</td>
                  <td>{p.iodepth}</td>
                  <td>{humanIops(p.best_iops)}</td>
                  <td>{humanBps(p.best_bw_bytes)}</td>
                  <td className="mono">{p.sample_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>{t("models.comparePhase")}</h3>
        <div className="dim" style={{ fontSize: 11, marginBottom: 8 }}>
          {t("models.phaseSamplesHelp")}
        </div>
        <div className="row" style={{ alignItems: "center", marginBottom: 12 }}>
          <label className="dim" style={{ fontSize: 12 }}>{t("models.selectPhase")}:</label>
          <select
            value={selectedPhase}
            onChange={(e) => setSelectedPhase(e.target.value)}
          >
            <option value="">—</option>
            {phases.map((p) => (
              <option key={p.phase_name} value={p.phase_name}>
                {p.phase_name} ({humanBytes(p.block_size)}/QD{p.iodepth})
              </option>
            ))}
          </select>
        </div>
        {selectedPhase && compareOption ? (
          <ReactECharts style={{ height: 320 }} option={compareOption} notMerge lazyUpdate />
        ) : selectedPhase ? (
          <div className="dim">{t("common.loading")}</div>
        ) : null}
      </div>

      <div className="card">
        <h3>{t("models.runs")}</h3>
        {m.runs.length === 0 ? (
          <div className="dim">{t("models.noRuns")}</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>{t("runs.profile")}</th>
                <th>{t("runs.status")}</th>
                <th>{t("runs.startedAt")}</th>
                <th>{t("runs.finishedAt")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {m.runs.map((r) => (
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
                  <td className="dim">
                    {r.started_at ? dayjs(r.started_at).format("YYYY-MM-DD HH:mm") : "—"}
                  </td>
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
