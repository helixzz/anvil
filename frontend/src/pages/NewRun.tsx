import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, type Device, type Profile } from "@/api";
import { formatDuration, humanBytes } from "@/lib/format";
import { ProfilePicker } from "@/components/ProfilePicker";

export default function NewRun() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const devicesQ = useQuery({ queryKey: ["devices"], queryFn: api.listDevices });
  const profilesQ = useQuery({ queryKey: ["profiles"], queryFn: api.listProfiles });

  const [deviceId, setDeviceId] = useState<string>("");
  const [profileName, setProfileName] = useState<string>("quick");
  const [serialLast6, setSerialLast6] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: api.createRun,
    onSuccess: (run) => navigate(`/runs/${run.id}`),
    onError: (err: Error) => setError(err.message),
  });

  const testable: Device[] = (devicesQ.data ?? []).filter((d) => d.is_testable);
  const selectedDevice = testable.find((d) => d.id === deviceId);
  const selectedProfile: Profile | undefined = profilesQ.data?.find(
    (p) => p.name === profileName,
  );

  function submit() {
    if (!deviceId || !profileName) return;
    create.mutate({
      device_id: deviceId,
      profile_name: profileName,
      confirm_serial_last6: selectedProfile?.destructive ? serialLast6 : undefined,
    });
  }

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <h2>{t("newRun.title")}</h2>
      </div>

      {testable.length === 0 ? (
        <div className="card dim">{t("newRun.noTestable")}</div>
      ) : (
        <div className="card col" style={{ gap: 16 }}>
          <div className="col">
            <label className="dim" style={{ fontSize: 12 }}>
              {t("newRun.pickDevice")}
            </label>
            <select value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
              <option value="">—</option>
              {testable.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.model} · {d.serial} · {humanBytes(d.capacity_bytes)} ·{" "}
                  {d.current_device_path}
                </option>
              ))}
            </select>
          </div>

          <div className="col">
            <label className="dim" style={{ fontSize: 12 }}>
              {t("newRun.pickProfile")}
            </label>
            <ProfilePicker
              profiles={profilesQ.data ?? []}
              value={profileName}
              onChange={setProfileName}
              disabled={profilesQ.isLoading}
            />
          </div>

          {selectedProfile && (
            <div className="card" style={{ background: "var(--bg-elev-2)" }}>
              <h3>{selectedProfile.title}</h3>
              <div className="dim" style={{ marginBottom: 8 }}>
                {selectedProfile.description}
              </div>
              <div style={{ fontSize: 13, marginBottom: 8 }}>
                {t("newRun.estimatedDuration")}:{" "}
                <span className="mono">
                  {formatDuration(selectedProfile.estimated_duration_seconds)}
                </span>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>Phase</th>
                    <th>Pattern</th>
                    <th>BS</th>
                    <th>QD</th>
                    <th>Jobs</th>
                    <th>Runtime</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedProfile.phases.map((p) => (
                    <tr key={p.name}>
                      <td className="mono">{p.name}</td>
                      <td>{p.pattern}</td>
                      <td>{humanBytes(p.block_size)}</td>
                      <td>{p.iodepth}</td>
                      <td>{p.numjobs}</td>
                      <td>{p.runtime_s}s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {selectedProfile?.destructive && selectedDevice && (
            <div className="card" style={{ background: "#3b1820", border: "1px solid #7f1d1d" }}>
              <div className="col">
                <div>{t("newRun.destructiveWarning")}</div>
                <div className="mono dim" style={{ fontSize: 12 }}>
                  {selectedDevice.serial}
                </div>
                <input
                  value={serialLast6}
                  onChange={(e) => setSerialLast6(e.target.value)}
                  placeholder={t("newRun.serialInputPlaceholder")}
                  maxLength={6}
                />
              </div>
            </div>
          )}

          {error && <div className="badge badge-err">{error}</div>}

          <div className="row">
            <button
              className="btn-primary"
              disabled={!deviceId || !profileName || create.isPending}
              onClick={submit}
            >
              {create.isPending ? t("common.loading") : t("newRun.launch")}
            </button>
            <button onClick={() => navigate(-1)}>{t("common.cancel")}</button>
          </div>
        </div>
      )}
    </div>
  );
}
