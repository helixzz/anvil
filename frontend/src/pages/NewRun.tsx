import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, type Device } from "@/api";
import { formatDuration, humanBytes } from "@/lib/format";
import { MultiSelect, type MultiSelectOption } from "@/components/MultiSelect";

export default function NewRun() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const devicesQ = useQuery({ queryKey: ["devices"], queryFn: api.listDevices });
  const profilesQ = useQuery({ queryKey: ["profiles"], queryFn: api.listProfiles });

  const [deviceIds, setDeviceIds] = useState<Set<string>>(new Set());
  const [profileNames, setProfileNames] = useState<Set<string>>(new Set());
  const [serialMap, setSerialMap] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: api.batchCreateRuns,
    onSuccess: () => navigate("/runs"),
    onError: (err: Error) => setError(err.message),
  });

  const testable: Device[] = (devicesQ.data ?? []).filter((d) => d.is_testable);
  const profiles = profilesQ.data ?? [];

  const deviceOptions: MultiSelectOption[] = testable.map((d) => ({
    value: d.id,
    label: `${d.model} · ${d.serial}`,
    sub: `${humanBytes(d.capacity_bytes)} · ${d.current_device_path || "—"}`,
  }));

  const profileOptions: MultiSelectOption[] = profiles.map((p) => ({
    value: p.name,
    label: `${p.title} ${p.destructive ? "⚠" : ""}`,
    sub: `${formatDuration(p.estimated_duration_seconds)} · ${p.phases.length} phases`,
  }));

  const selectedDevices = testable.filter((d) => deviceIds.has(d.id));
  const selectedProfiles = profiles.filter((p) => profileNames.has(p.name));
  const destructiveProfiles = selectedProfiles.filter((p) => p.destructive);
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
        <h2>{t("newRun.title")}</h2>
        <div className="dim" style={{ fontSize: 12 }}>
          {comboCount > 0
            ? `${deviceIds.size}d × ${profileNames.size}p = ${comboCount} run(s)`
            : "Select device(s) and profile(s) below"}
        </div>
      </div>

      {testable.length === 0 ? (
        <div className="card dim">{t("newRun.noTestable")}</div>
      ) : (
        <div className="col" style={{ gap: 16 }}>
          <div className="card">
            <div className="dim" style={{ fontSize: 12, marginBottom: 8 }}>
              {t("newRun.pickDevice")}
            </div>
            <MultiSelect
              options={deviceOptions}
              selected={deviceIds}
              onChange={setDeviceIds}
              placeholder="Pick device(s)…"
            />
          </div>

          <div className="card">
            <div className="dim" style={{ fontSize: 12, marginBottom: 8 }}>
              {t("newRun.pickProfile")}
            </div>
            <MultiSelect
              options={profileOptions}
              selected={profileNames}
              onChange={setProfileNames}
              placeholder="Pick profile(s)…"
              disabled={profilesQ.isLoading}
            />
          </div>

          {selectedProfiles.length > 0 && (
            <div className="card" style={{ background: "var(--bg-elev-2)" }}>
              {selectedProfiles.map((p) => (
                <div key={p.name} style={{ marginBottom: 16 }}>
                  <h3 style={{ margin: "0 0 4px 0" }}>
                    {p.title}{" "}
                    {p.destructive && (
                      <span className="badge badge-err" style={{ fontSize: 10 }}>
                        destructive
                      </span>
                    )}
                  </h3>
                  <div className="dim" style={{ fontSize: 12, marginBottom: 6 }}>
                    {p.description}
                  </div>
                  <div style={{ fontSize: 12, marginBottom: 6 }}>
                    {t("newRun.estimatedDuration")}:{" "}
                    <span className="mono">{formatDuration(p.estimated_duration_seconds)}</span>{" "}
                    · <span className="mono">{p.phases.length} phases</span>
                  </div>
                  {selectedProfiles.length <= 2 && (
                    <table>
                      <thead>
                        <tr>
                          <th>Phase</th><th>Pattern</th><th>BS</th><th>QD</th><th>Jobs</th><th>Runtime</th>
                        </tr>
                      </thead>
                      <tbody>
                        {p.phases.map((ph) => (
                          <tr key={ph.name}>
                            <td className="mono" style={{ fontSize: 11 }}>{ph.name}</td>
                            <td style={{ fontSize: 12 }}>{ph.pattern}</td>
                            <td style={{ fontSize: 12 }}>{humanBytes(ph.block_size)}</td>
                            <td style={{ fontSize: 12 }}>{ph.iodepth}</td>
                            <td style={{ fontSize: 12 }}>{ph.numjobs}</td>
                            <td style={{ fontSize: 12 }}>{ph.runtime_s}s</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              ))}
            </div>
          )}

          {needsSerial && (
            <div className="card" style={{ background: "#3b1820", border: "1px solid #7f1d1d" }}>
              <div style={{ marginBottom: 12, fontSize: 13 }}>
                Destructive profile(s): {destructiveProfiles.map((p) => p.title).join(", ")}.
                Enter the last 6 characters of each device serial:
              </div>
              <div className="col" style={{ gap: 6 }}>
                {selectedDevices.map((d) => (
                  <div key={d.id} className="row" style={{ alignItems: "center", gap: 8 }}>
                    <span className="mono" style={{ fontSize: 12, minWidth: 200 }}>
                      {d.model} · {d.serial}
                    </span>
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
              {create.isPending
                ? t("common.loading")
                : comboCount > 0
                  ? `Launch ${comboCount} run(s)`
                  : t("newRun.launch")}
            </button>
            <button onClick={() => navigate(-1)}>{t("common.cancel")}</button>
          </div>
        </div>
      )}
    </div>
  );
}
