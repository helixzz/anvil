import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, type Device } from "@/api";
import { formatDuration, humanBytes } from "@/lib/format";

type DestructiveSerialMap = Record<string, string>;

export default function NewRun() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const devicesQ = useQuery({ queryKey: ["devices"], queryFn: api.listDevices });
  const profilesQ = useQuery({ queryKey: ["profiles"], queryFn: api.listProfiles });

  const [deviceIds, setDeviceIds] = useState<Set<string>>(new Set());
  const [profileNames, setProfileNames] = useState<Set<string>>(new Set("quick"));
  const [serialMap, setSerialMap] = useState<DestructiveSerialMap>({});
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: api.batchCreateRuns,
    onSuccess: (result) => {
      navigate(`/runs?batch=${result.run_ids.length}`)
    },
    onError: (err: Error) => setError(err.message),
  });

  const testable: Device[] = (devicesQ.data ?? []).filter((d) => d.is_testable);
  const profiles = profilesQ.data ?? [];

  function toggleDevice(id: string) {
    setDeviceIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
        setSerialMap((m) => { const n = { ...m }; delete n[id]; return n; });
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function toggleProfile(name: string) {
    setProfileNames((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  const selectedDevices = testable.filter((d) => deviceIds.has(d.id));
  const destructiveProfiles = profiles.filter((p) => profileNames.has(p.name) && p.destructive);
  const needsSerial = selectedDevices.length > 0 && destructiveProfiles.length > 0;
  const comboCount = deviceIds.size * profileNames.size;

  function submit() {
    if (deviceIds.size === 0 || profileNames.size === 0) return;
    let confirm: Record<string, string> | undefined;
    if (needsSerial) {
      confirm = { ...serialMap };
      const missing = selectedDevices.filter((d) => !confirm?.[d.id]);
      if (missing.length > 0) {
        setError(`Enter serial confirmation for: ${missing.map((d) => d.serial).join(", ")}`);
        return;
      }
    }
    setError(null);
    create.mutate({
      device_ids: Array.from(deviceIds),
      profile_names: Array.from(profileNames),
      confirm_serial: confirm,
    });
  }

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <h2>Batch new runs</h2>
        <div className="dim" style={{ fontSize: 12 }}>
          {comboCount > 0 ? `${deviceIds.size} device(s) × ${profileNames.size} profile(s) = ${comboCount} run(s)` : "Select devices and profiles"}
        </div>
      </div>

      {testable.length === 0 ? (
        <div className="card dim">{t("newRun.noTestable")}</div>
      ) : (
        <div className="col" style={{ gap: 20 }}>
          <div className="card">
            <h4 style={{ margin: "0 0 8px 0" }}>Devices</h4>
            <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
              {testable.map((d) => (
                <button
                  key={d.id}
                  onClick={() => toggleDevice(d.id)}
                  className={deviceIds.has(d.id) ? "btn-primary" : ""}
                  style={{ fontSize: 12 }}
                >
                  {d.model} · {d.serial} · {humanBytes(d.capacity_bytes)}
                </button>
              ))}
            </div>
          </div>

          <div className="card">
            <h4 style={{ margin: "0 0 8px 0" }}>Profiles</h4>
            <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
              {profiles.map((p) => (
                <button
                  key={p.name}
                  onClick={() => toggleProfile(p.name)}
                  className={profileNames.has(p.name) ? "btn-primary" : ""}
                  style={{ fontSize: 12 }}
                  title={p.description}
                >
                  {p.title} {p.destructive ? "⚠" : ""} · {formatDuration(p.estimated_duration_seconds)}
                </button>
              ))}
            </div>
          </div>

          {needsSerial && (
            <div className="card" style={{ background: "#3b1820", border: "1px solid #7f1d1d" }}>
              <div style={{ marginBottom: 12 }}>
                Destructive profile(s) selected: {destructiveProfiles.map((p) => p.title).join(", ")}.
                Enter the last 6 characters of each device serial:
              </div>
              <div className="col" style={{ gap: 8 }}>
                {selectedDevices.map((d) => (
                  <div key={d.id} className="row" style={{ alignItems: "center", gap: 8 }}>
                    <span className="mono" style={{ fontSize: 12, minWidth: 180 }}>{d.model} · {d.serial}</span>
                    <input
                      value={serialMap[d.id] || ""}
                      onChange={(e) => setSerialMap((m) => ({ ...m, [d.id]: e.target.value }))}
                      placeholder="e.g. A1B2C3"
                      maxLength={6}
                      style={{ width: 100, fontSize: 13 }}
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {error && <div className="badge badge-err" style={{ padding: 8 }}>{error}</div>}

          <div className="row" style={{ gap: 8 }}>
            <button
              className="btn-primary"
              disabled={deviceIds.size === 0 || profileNames.size === 0 || create.isPending}
              onClick={submit}
            >
              {create.isPending ? t("common.loading") : `Launch ${comboCount} run(s)`}
            </button>
            <button onClick={() => navigate(-1)}>{t("common.cancel")}</button>
          </div>
        </div>
      )}
    </div>
  );
}
