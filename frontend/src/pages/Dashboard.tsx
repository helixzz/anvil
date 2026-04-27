import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import dayjs from "dayjs";
import ReactECharts from "echarts-for-react";
import type { ReactNode } from "react";

import { api, type LeaderboardCategory } from "@/api";
import { humanBps, humanBytes, humanIops, humanNs } from "@/lib/format";

function KpiCard({
  title,
  value,
  sub,
}: {
  title: string;
  value: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="card stretch" style={{ minWidth: 150 }}>
      <h3>{title}</h3>
      <div className="mono" style={{ fontSize: 22, fontWeight: 600 }}>
        {value}
      </div>
      {sub && (
        <div className="dim" style={{ fontSize: 11, marginTop: 4 }}>
          {sub}
        </div>
      )}
    </div>
  );
}

function LeaderboardPanel({
  categoryKey,
  data,
}: {
  categoryKey: string;
  data: LeaderboardCategory;
}) {
  const { t } = useTranslation();
  if (data.entries.length === 0) {
    return (
      <div className="card">
        <h3>{data.title}</h3>
        <div className="dim">{t("dashboard.noData")}</div>
      </div>
    );
  }
  const isLatency = data.metric.endsWith("_ns");
  const isBw = data.metric.includes("_bw_");
  const fmt = isLatency ? humanNs : isBw ? humanBps : humanIops;
  return (
    <div className="card">
      <h3>{data.title}</h3>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>{t("dashboard.device")}</th>
            <th>{t("dashboard.value")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {data.entries.map((e, i) => (
            <tr key={`${categoryKey}-${e.run_id}`}>
              <td className="mono">{i + 1}</td>
              <td>
                <Link to={`/devices/${encodeURIComponent(e.device_id)}`}>
                  <span className="badge">{e.brand}</span>{" "}
                  <span className="mono" style={{ fontSize: 12 }}>
                    {e.model}
                  </span>
                </Link>
              </td>
              <td className="mono">{e.value != null ? fmt(e.value) : "—"}</td>
              <td>
                <Link to={`/runs/${e.run_id}`} style={{ fontSize: 12 }}>
                  →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ActivityChart() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["dashboard-activity"], queryFn: () => api.activity(30) });
  if (!q.data) return null;
  const labels = q.data.series.map((d) => d.day.slice(5));
  const complete = q.data.series.map((d) => d.complete);
  const failed = q.data.series.map((d) => d.failed);
  const aborted = q.data.series.map((d) => d.aborted);

  return (
    <div className="card">
      <h3>{t("dashboard.activity")}</h3>
      <ReactECharts
        style={{ height: 220 }}
        notMerge
        lazyUpdate
        option={{
          animation: false,
          grid: { top: 40, right: 20, bottom: 30, left: 40 },
          tooltip: { trigger: "axis", backgroundColor: "#111a2e", borderColor: "#233256", textStyle: { color: "#e2e8f0" } },
          legend: { top: 8, textStyle: { color: "#94a3b8" } },
          xAxis: {
            type: "category",
            data: labels,
            axisLine: { lineStyle: { color: "#233256" } },
            axisLabel: { color: "#94a3b8", fontSize: 10 },
          },
          yAxis: {
            type: "value",
            axisLine: { lineStyle: { color: "#233256" } },
            axisLabel: { color: "#94a3b8" },
            splitLine: { lineStyle: { color: "#1a2440" } },
          },
          series: [
            { name: t("runs.completed"), type: "bar", stack: "runs", data: complete, itemStyle: { color: "#4ade80" } },
            { name: t("runs.failed"), type: "bar", stack: "runs", data: failed, itemStyle: { color: "#f87171" } },
            { name: t("runs.aborted"), type: "bar", stack: "runs", data: aborted, itemStyle: { color: "#facc15" } },
          ],
        }}
      />
    </div>
  );
}

function StatusDot({ color }: { color: string }) {
  return (
    <span
      style={{
        display: "inline-block",
        width: 10,
        height: 10,
        borderRadius: "50%",
        background: color,
        marginRight: 6,
        verticalAlign: "middle",
      }}
    />
  );
}

export default function Dashboard() {
  const { t } = useTranslation();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const fleet = useQuery({ queryKey: ["dashboard-fleet"], queryFn: api.fleetStats });
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api.listRuns({}) });
  const board = useQuery({ queryKey: ["dashboard-leaderboards"], queryFn: () => api.leaderboards(5) });
  const degraded = useQuery({
    queryKey: ["dashboard-degraded"],
    queryFn: () => api.pcieDegraded(),
  });
  const env = useQuery({ queryKey: ["environment"], queryFn: api.getEnvironment });
  const alarms = useQuery({ queryKey: ["dashboard-alarms"], queryFn: () => api.alarms(24) });

  const envDot = env.data
    ? env.data.summary.fail > 0
      ? "#f87171"
      : env.data.summary.warn > 0
        ? "#facc15"
        : "#4ade80"
    : "#6b7280";

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <h2>{t("nav.dashboard")}</h2>
      </div>

      <div className="row">
        <KpiCard
          title={t("dashboard.testableDevices")}
          value={
            fleet.data
              ? `${fleet.data.testable_device_count} / ${fleet.data.device_count}`
              : "—"
          }
          sub={fleet.data ? `${fleet.data.distinct_models} ${t("dashboard.models")}` : undefined}
        />
        <KpiCard
          title={t("dashboard.brandsSeen")}
          value={fleet.data?.distinct_brands ?? "—"}
        />
        <KpiCard
          title={t("dashboard.totalRuns")}
          value={fleet.data?.total_runs ?? "—"}
          sub={
            fleet.data
              ? `${fleet.data.complete_runs} ok · ${fleet.data.failed_runs} fail · ${fleet.data.aborted_runs} aborted`
              : undefined
          }
        />
        <KpiCard
          title={t("dashboard.bytesWritten")}
          value={fleet.data ? humanBytes(fleet.data.approx_bytes_written) : "—"}
          sub={t("dashboard.approxBw")}
        />
        <KpiCard
          title={t("status.runner")}
          value={
            <>
              <StatusDot color={status.data?.runner_connected ? "#4ade80" : "#f87171"} />
              {status.data?.runner_connected
                ? t("status.runnerConnected")
                : t("status.runnerDisconnected")}
            </>
          }
          sub={status.data?.simulation_mode ? t("status.simulation") : undefined}
        />
        <KpiCard
          title={t("dashboard.envHealth")}
          value={
            <Link to="/system" style={{ textDecoration: "none" }}>
              <StatusDot color={envDot} />
              {env.data
                ? `${env.data.summary.pass}/${env.data.summary.total} ${t("dashboard.pass")}`
                : "—"}
            </Link>
          }
          sub={
            env.data
              ? `${env.data.summary.warn} warn · ${env.data.summary.fail} fail`
              : undefined
          }
        />
      </div>

      {degraded.data && degraded.data.length > 0 && (
        <div className="card" style={{ borderColor: "#78350f", background: "#422006" }}>
          <h3 style={{ color: "#fde68a" }}>
            ⚠ {t("dashboard.pcieDegradedTitle")} ({degraded.data.length})
          </h3>
          <div className="dim" style={{ fontSize: 11, marginBottom: 8 }}>
            {t("dashboard.pcieDegradedHelp")}
          </div>
          <table>
            <thead>
              <tr>
                <th>{t("dashboard.device")}</th>
                <th>{t("pcie.capability")}</th>
                <th>{t("pcie.status")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {degraded.data.map((e) => {
                const cap = e.capability as { pcie_gen?: string; width?: number } | null;
                const st = e.status as { pcie_gen?: string; width?: number } | null;
                return (
                  <tr key={e.device_id}>
                    <td>
                      <Link to={`/devices/${encodeURIComponent(e.device_id)}`}>
                        <span className="badge">{e.brand}</span>{" "}
                        <span className="mono" style={{ fontSize: 12 }}>
                          {e.model}
                        </span>
                      </Link>
                    </td>
                    <td className="mono">
                      {cap?.pcie_gen} x{cap?.width}
                    </td>
                    <td className="mono" style={{ color: "#fde68a" }}>
                      {st?.pcie_gen} x{st?.width}
                    </td>
                    <td>
                      <Link to={`/devices/${encodeURIComponent(e.device_id)}`}>→</Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {alarms.data && alarms.data.length > 0 && (
        <div className="card" style={{ borderColor: "#7f1d1d", background: "#3b1820" }}>
          <h3 style={{ color: "#fca5a5" }}>⚠ {t("dashboard.alarmsTitle")}</h3>
          <div className="dim" style={{ fontSize: 11, marginBottom: 8 }}>
            {t("dashboard.alarmsHelp")}
          </div>
          <table>
            <thead>
              <tr>
                <th>{t("dashboard.device")}</th>
                <th>{t("runs.profile")}</th>
                <th>{t("runs.status")}</th>
                <th>{t("runs.finishedAt")}</th>
                <th>{t("runs.errorMessage")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {alarms.data.map((a) => (
                <tr key={a.run_id}>
                  <td className="mono" style={{ fontSize: 12 }}>{a.model ?? "—"}</td>
                  <td>{a.profile}</td>
                  <td>
                    <span className={`badge badge-${a.status === "aborted" ? "warn" : "err"}`}>
                      {a.status}
                    </span>
                  </td>
                  <td className="dim">
                    {a.finished_at ? dayjs(a.finished_at).format("MM-DD HH:mm") : "—"}
                  </td>
                  <td className="dim mono" style={{ fontSize: 11 }}>
                    {(a.error_message ?? "").slice(0, 80)}
                  </td>
                  <td>
                    <Link to={`/runs/${a.run_id}`}>→</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ActivityChart />

      <div className="row" style={{ gap: 20 }}>
        {board.data &&
          Object.entries(board.data).map(([k, v]) => (
            <div key={k} style={{ flex: "1 1 400px", minWidth: 400 }}>
              <LeaderboardPanel categoryKey={k} data={v} />
            </div>
          ))}
      </div>

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>{t("dashboard.recentRuns")}</h3>
          <Link to="/runs/new">
            <button className="btn-primary">+ {t("nav.newRun")}</button>
          </Link>
        </div>
        {runs.isLoading ? (
          <div className="dim">{t("common.loading")}</div>
        ) : !runs.data?.items || runs.data.items.length === 0 ? (
          <div className="dim">{t("runs.noRuns")}</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>{t("runs.device")}</th>
                <th>{t("runs.profile")}</th>
                <th>{t("runs.status")}</th>
                <th>{t("runs.queuedAt")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {runs.data.items.slice(0, 10).map((r) => (
                <tr key={r.id}>
                  <td>
                    <div className="mono">{r.device_model}</div>
                    <div className="dim mono" style={{ fontSize: 11 }}>{r.device_serial}</div>
                  </td>
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
                  <td className="dim">{dayjs(r.queued_at).format("YYYY-MM-DD HH:mm")}</td>
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
