import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api";

interface ScheduleRow {
  id: string; name: string; device_id: string; profile_name: string;
  enabled: boolean; interval_hours: number;
  last_run_at: string | null; next_run_at: string | null;
}

const INTERVALS = [
  { v: 1, label: "1 hour" },
  { v: 6, label: "6 hours" },
  { v: 24, label: "daily" },
  { v: 168, label: "weekly" },
  { v: 720, label: "monthly (~30 days)" },
];

export default function Schedules() {
  const qc = useQueryClient();
  const q = useQuery<ScheduleRow[]>({ queryKey: ["schedules"], queryFn: api.listSchedules });
  const devicesQ = useQuery({ queryKey: ["devices"], queryFn: api.listDevices });

  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [profile, setProfile] = useState("snia_quick_pts");
  const [intervalH, setIntervalH] = useState(168);
  const [enabled, setEnabled] = useState(true);

  const saveMut = useMutation({
    mutationFn: async () => {
      const body = { name, device_id: deviceId, profile_name: profile, interval_hours: intervalH, enabled };
      if (editId) return api.updateSchedule(editId, body);
      return api.createSchedule(body);
    },
    onSuccess: () => { setShowForm(false); setEditId(null); qc.invalidateQueries({ queryKey: ["schedules"] }); },
  });

  const delMut = useMutation({
    mutationFn: (id: string) => api.deleteSchedule(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedules"] }),
  });

  function openNew() {
    setEditId(null); setName(""); setDeviceId(""); setProfile("snia_quick_pts");
    setIntervalH(168); setEnabled(true); setShowForm(true);
  }

  function openEdit(r: ScheduleRow) {
    setEditId(r.id); setName(r.name); setDeviceId(r.device_id); setProfile(r.profile_name);
    setIntervalH(r.interval_hours); setEnabled(r.enabled); setShowForm(true);
  }

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <div>
          <h2>Scheduled runs</h2>
          <div className="dim" style={{ fontSize: 12 }}>
            Auto-start benchmarks at regular intervals. The queue runs only one run at a time; a scheduled run that arrives while another is in progress will queue behind it.
          </div>
        </div>
        <button className="btn-primary" onClick={openNew}>+ New schedule</button>
      </div>

      {showForm && (
        <div className="card">
          <h3>{editId ? "Edit schedule" : "New schedule"}</h3>
          <div className="col" style={{ gap: 10 }}>
            <input placeholder="Name (e.g. Weekly SNIA check)" value={name} onChange={(e) => setName(e.target.value)} />
            <select value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
              <option value="">Pick device</option>
              {(devicesQ.data ?? []).map((d) => <option key={d.id} value={d.id}>{d.brand} {d.model} ({d.serial})</option>)}
            </select>
            <div className="row" style={{ gap: 8 }}>
              <select value={profile} onChange={(e) => setProfile(e.target.value)}>
                <option value="snia_quick_pts">SNIA Quick PTS (~35 min)</option>
                <option value="sweep_quick">Quick Sweep (~5 min)</option>
                <option value="sweep_full">Full Sweep (~45 min)</option>
                <option value="endurance_soak">Endurance Soak (~2 h)</option>
              </select>
              <select value={intervalH} onChange={(e) => setIntervalH(Number(e.target.value))}>
                {INTERVALS.map((iv) => <option key={iv.v} value={iv.v}>{iv.label}</option>)}
              </select>
            </div>
            <label><input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> Enabled</label>
            <div className="row" style={{ gap: 8 }}>
              <button className="btn-primary" onClick={() => saveMut.mutate()} disabled={saveMut.isPending}>
                {saveMut.isPending ? "Saving…" : "Save"}
              </button>
              <button onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {q.isLoading ? <div className="dim">Loading…</div> : !q.data || q.data.length === 0 ? (
        <div className="card dim" style={{ textAlign: "center", padding: 40 }}>No scheduled runs yet.</div>
      ) : (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Name</th><th>Device</th><th>Profile</th><th>Interval</th>
                <th>Next run</th><th>Last run</th><th />
              </tr>
            </thead>
            <tbody>
              {q.data.map((r) => (
                <tr key={r.id}>
                  <td>{r.name} {r.enabled ? "" : <span className="badge badge-err">paused</span>}</td>
                  <td className="mono" style={{ fontSize: 12 }}>{r.device_id.slice(-8)}</td>
                  <td>{r.profile_name}</td>
                  <td>{r.interval_hours}h</td>
                  <td className="dim mono" style={{ fontSize: 11 }}>{r.next_run_at ? new Date(r.next_run_at).toLocaleString() : "—"}</td>
                  <td className="dim mono" style={{ fontSize: 11 }}>{r.last_run_at ? new Date(r.last_run_at).toLocaleString() : "—"}</td>
                  <td>
                    <button onClick={() => openEdit(r)} style={{ fontSize: 12 }}>Edit</button>
                    <button className="btn-danger" onClick={() => { if (window.confirm("Delete this schedule?")) delMut.mutate(r.id); }} style={{ fontSize: 12, marginLeft: 4 }}>Del</button>
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
