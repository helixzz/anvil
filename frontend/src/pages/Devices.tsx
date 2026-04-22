import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import dayjs from "dayjs";
import { api } from "@/api";
import { humanBytes } from "@/lib/format";

export default function Devices() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const q = useQuery({ queryKey: ["devices"], queryFn: api.listDevices });
  const rescan = useMutation({
    mutationFn: api.rescanDevices,
    onSuccess: (data) => client.setQueryData(["devices"], data),
  });

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <h2>{t("devices.title")}</h2>
        <button className="btn-primary" onClick={() => rescan.mutate()} disabled={rescan.isPending}>
          {rescan.isPending ? t("common.loading") : t("common.rescan")}
        </button>
      </div>

      {q.isLoading ? (
        <div className="dim">{t("common.loading")}</div>
      ) : !q.data || q.data.length === 0 ? (
        <div className="card dim">{t("devices.noDevices")}</div>
      ) : (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>{t("devices.model")}</th>
                <th>{t("devices.serial")}</th>
                <th>{t("devices.firmware")}</th>
                <th>{t("devices.size")}</th>
                <th>{t("devices.path")}</th>
                <th>{t("devices.protocol")}</th>
                <th>{t("devices.testable")}</th>
                <th>{t("devices.lastSeen")}</th>
              </tr>
            </thead>
            <tbody>
              {q.data.map((d) => (
                <tr key={d.id}>
                  <td>{d.model}</td>
                  <td className="mono" style={{ fontSize: 12 }}>{d.serial}</td>
                  <td className="mono" style={{ fontSize: 12 }}>{d.firmware ?? "—"}</td>
                  <td>{humanBytes(d.capacity_bytes)}</td>
                  <td className="mono" style={{ fontSize: 12 }}>{d.current_device_path ?? "—"}</td>
                  <td>{d.protocol}</td>
                  <td>
                    {d.is_testable ? (
                      <span className="badge badge-ok">{t("devices.testable")}</span>
                    ) : (
                      <span className="badge badge-warn" title={d.exclusion_reason ?? ""}>
                        {t("devices.excluded")}
                      </span>
                    )}
                    {d.exclusion_reason && !d.is_testable && (
                      <div className="dim" style={{ fontSize: 11 }}>{d.exclusion_reason}</div>
                    )}
                  </td>
                  <td className="dim">{dayjs(d.last_seen).format("YYYY-MM-DD HH:mm")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
