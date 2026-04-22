import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import dayjs from "dayjs";

import { api } from "@/api";
import { formatDuration } from "@/lib/format";

export default function Dashboard() {
  const { t } = useTranslation();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.listRuns });

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <h2>{t("nav.dashboard")}</h2>
      </div>

      <div className="row">
        <div className="card stretch">
          <h3>{t("status.runner")}</h3>
          <div className="mono" style={{ fontSize: 20 }}>
            {status.data?.runner_connected
              ? t("status.runnerConnected")
              : t("status.runnerDisconnected")}
          </div>
        </div>
        <div className="card stretch">
          <h3>{t("status.devices")}</h3>
          <div className="mono" style={{ fontSize: 20 }}>{status.data?.device_count ?? "—"}</div>
        </div>
        <div className="card stretch">
          <h3>{t("status.queued")}</h3>
          <div className="mono" style={{ fontSize: 20 }}>{status.data?.queued_count ?? "—"}</div>
        </div>
        <div className="card stretch">
          <h3>{t("status.running")}</h3>
          <div className="mono" style={{ fontSize: 20 }}>{status.data?.running_count ?? "—"}</div>
        </div>
      </div>

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>{t("runs.title")}</h3>
          <Link to="/runs/new"><button className="btn-primary">+ {t("nav.newRun")}</button></Link>
        </div>
        {runs.isLoading ? (
          <div className="dim">{t("common.loading")}</div>
        ) : !runs.data || runs.data.length === 0 ? (
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
              {runs.data.slice(0, 10).map((r) => (
                <tr key={r.id}>
                  <td>
                    <div className="mono">{r.device_model}</div>
                    <div className="dim mono" style={{ fontSize: 11 }}>{r.device_serial}</div>
                  </td>
                  <td>{r.profile_name}</td>
                  <td><span className={`badge badge-${r.status === "complete" ? "ok" : r.status === "failed" ? "err" : r.status === "running" ? "running" : "queued"}`}>{r.status}</span></td>
                  <td className="dim">{dayjs(r.queued_at).format("YYYY-MM-DD HH:mm")}</td>
                  <td><Link to={`/runs/${r.id}`}>{t("runs.viewReport")} →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="dim" style={{ fontSize: 12 }}>
        {t("status.version")}: <span className="mono">{status.data?.version ?? "—"}</span>
        &nbsp;·&nbsp;uptime: <span className="mono">{formatDuration(status.data?.uptime_seconds ?? 0)}</span>
      </div>
    </div>
  );
}
