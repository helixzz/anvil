import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import dayjs from "dayjs";
import { api } from "@/api";
import { humanBytes } from "@/lib/format";

function mountPoints(meta: Record<string, unknown> | undefined | null): string[] {
  const raw = meta?.mount_points;
  if (!Array.isArray(raw)) return [];
  return raw.filter((v): v is string => typeof v === "string" && v.length > 0);
}

export default function Devices() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const q = useQuery({ queryKey: ["devices"], queryFn: api.listDevices });
  const runnersQ = useQuery({ queryKey: ["runners"], queryFn: api.listRunners });

  const [hostFilter, setHostFilter] = useState<string>("");
  const [rescanTarget, setRescanTarget] = useState<string>("");
  const [rescanErrors, setRescanErrors] = useState<Record<string, string> | null>(null);

  const runnerNames = useMemo(() => {
    const m = new Map<string, string>();
    for (const r of runnersQ.data ?? []) m.set(r.id, r.name);
    return m;
  }, [runnersQ.data]);

  const rescan = useMutation({
    mutationFn: (runnerId?: string) => api.rescanDevices(runnerId),
    onSuccess: (data) => {
      client.setQueryData(["devices"], data.devices);
      setRescanErrors(data.errors && Object.keys(data.errors).length > 0 ? data.errors : null);
    },
  });

  const filtered = useMemo(() => {
    const all = q.data ?? [];
    if (!hostFilter) return all;
    return all.filter((d) => (d.runner_id ?? "") === hostFilter);
  }, [q.data, hostFilter]);

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <h2>{t("devices.title")}</h2>
        <div className="row" style={{ gap: 8, alignItems: "center" }}>
          <span className="dim" style={{ fontSize: 12 }}>{t("devices.host")}:</span>
          <select value={hostFilter} onChange={(e) => setHostFilter(e.target.value)}>
            <option value="">{t("devices.allHosts")}</option>
            {(runnersQ.data ?? []).map((r) => (
              <option key={r.id} value={r.id}>{r.name}</option>
            ))}
          </select>
          <select
            value={rescanTarget}
            onChange={(e) => setRescanTarget(e.target.value)}
            title={t("common.rescan")}
          >
            <option value="">{t("devices.allHosts")}</option>
            {(runnersQ.data ?? []).map((r) => (
              <option key={r.id} value={r.id}>{r.name}</option>
            ))}
          </select>
          <button
            className="btn-primary"
            onClick={() => rescan.mutate(rescanTarget || undefined)}
            disabled={rescan.isPending}
          >
            {rescan.isPending ? t("common.loading") : t("common.rescan")}
          </button>
        </div>
      </div>

      {rescanErrors && (
        <div className="card" style={{ borderColor: "#78350f", background: "rgba(66, 32, 6, 0.35)" }}>
          <div style={{ color: "#fde68a", fontSize: 13, marginBottom: 4 }}>
            {t("devices.rescanErrors")}
          </div>
          {Object.entries(rescanErrors).map(([runnerName, msg]) => (
            <div key={runnerName} className="mono" style={{ fontSize: 12 }}>
              {runnerName}: {msg}
            </div>
          ))}
        </div>
      )}

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
                <th>{t("devices.host")}</th>
                <th>{t("devices.mountPoints")}</th>
                <th>{t("devices.testable")}</th>
                <th>{t("devices.lastSeen")}</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((d) => {
                const mps = mountPoints(d.metadata_json as Record<string, unknown>);
                return (
                  <tr key={d.id}>
                    <td>
                      <Link to={`/devices/${encodeURIComponent(d.id)}`} className="mono" style={{ fontSize: 12 }}>
                        {d.model}
                      </Link>
                    </td>
                    <td className="mono" style={{ fontSize: 12 }}>{d.serial}</td>
                    <td className="mono" style={{ fontSize: 12 }}>{d.firmware ?? "—"}</td>
                    <td>{humanBytes(d.capacity_bytes)}</td>
                    <td className="mono" style={{ fontSize: 12 }}>{d.current_device_path ?? "—"}</td>
                    <td>{d.protocol}</td>
                    <td style={{ fontSize: 12 }}>
                      {d.runner_id ? (runnerNames.get(d.runner_id) ?? d.runner_id) : "—"}
                    </td>
                    <td>
                      {mps.length === 0 ? (
                        <span className="dim">—</span>
                      ) : (
                        <div className="col" style={{ gap: 2 }}>
                          {mps.map((m) => (
                            <span
                              key={m}
                              className="badge badge-warn mono"
                              style={{ fontSize: 11, width: "fit-content" }}
                            >
                              {m}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
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
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
