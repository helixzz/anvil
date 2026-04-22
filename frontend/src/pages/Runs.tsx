import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import dayjs from "dayjs";
import { api } from "@/api";

const badgeFor: Record<string, string> = {
  complete: "badge-ok",
  failed: "badge-err",
  aborted: "badge-err",
  running: "badge-running",
  preflight: "badge-running",
  queued: "badge-queued",
};

export default function Runs() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["runs"], queryFn: api.listRuns, refetchInterval: 2000 });

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <h2>{t("runs.title")}</h2>
        <Link to="/runs/new">
          <button className="btn-primary">+ {t("nav.newRun")}</button>
        </Link>
      </div>

      {q.isLoading ? (
        <div className="dim">{t("common.loading")}</div>
      ) : !q.data || q.data.length === 0 ? (
        <div className="card dim">{t("runs.noRuns")}</div>
      ) : (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>{t("runs.device")}</th>
                <th>{t("runs.profile")}</th>
                <th>{t("runs.status")}</th>
                <th>{t("runs.queuedAt")}</th>
                <th>{t("runs.startedAt")}</th>
                <th>{t("runs.finishedAt")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {q.data.map((r) => (
                <tr key={r.id}>
                  <td>
                    <div className="mono">{r.device_model}</div>
                    <div className="dim mono" style={{ fontSize: 11 }}>{r.device_serial}</div>
                  </td>
                  <td>{r.profile_name}</td>
                  <td>
                    <span className={`badge ${badgeFor[r.status] ?? "badge-queued"}`}>
                      {t(`status_labels.${r.status}` as const, r.status)}
                    </span>
                  </td>
                  <td className="dim">{dayjs(r.queued_at).format("HH:mm:ss")}</td>
                  <td className="dim">{r.started_at ? dayjs(r.started_at).format("HH:mm:ss") : "—"}</td>
                  <td className="dim">{r.finished_at ? dayjs(r.finished_at).format("HH:mm:ss") : "—"}</td>
                  <td>
                    <Link to={`/runs/${r.id}`}>{t("runs.viewReport")} →</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
