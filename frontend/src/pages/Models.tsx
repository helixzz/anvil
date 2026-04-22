import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import dayjs from "dayjs";
import { api } from "@/api";
import { humanBytes } from "@/lib/format";

export default function Models() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["models"], queryFn: api.listModels });

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <div>
          <h2>{t("models.title")}</h2>
          <div className="dim" style={{ fontSize: 12 }}>{t("models.subtitle")}</div>
        </div>
      </div>

      {q.isLoading ? (
        <div className="dim">{t("common.loading")}</div>
      ) : !q.data || q.data.length === 0 ? (
        <div className="card dim">{t("models.noModels")}</div>
      ) : (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>{t("models.brand")}</th>
                <th>{t("models.model")}</th>
                <th>{t("models.protocol")}</th>
                <th>{t("models.capacity")}</th>
                <th>{t("models.deviceCount")}</th>
                <th>{t("models.runCount")}</th>
                <th>{t("models.firmwares")}</th>
                <th>{t("models.lastRunAt")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {q.data.map((m) => (
                <tr key={m.slug}>
                  <td><span className="badge">{m.brand}</span></td>
                  <td className="mono">{m.model}</td>
                  <td>{m.protocol}</td>
                  <td>{humanBytes(m.capacity_bytes_typical)}</td>
                  <td className="mono">{m.device_count}</td>
                  <td className="mono">{m.run_count}</td>
                  <td className="dim mono" style={{ fontSize: 11 }}>
                    {m.firmwares.length === 0 ? "—" : m.firmwares.join(", ")}
                  </td>
                  <td className="dim">
                    {m.last_run_at
                      ? dayjs(m.last_run_at).format("YYYY-MM-DD HH:mm")
                      : "—"}
                  </td>
                  <td>
                    <Link to={`/models/${encodeURIComponent(m.slug)}`}>
                      {t("runs.viewReport")} →
                    </Link>
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
