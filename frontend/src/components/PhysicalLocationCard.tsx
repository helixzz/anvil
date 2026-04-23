import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Device } from "@/api";

export function PhysicalLocationCard({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["device", deviceId],
    queryFn: () => api.getDevice(deviceId),
    enabled: !!deviceId,
  });

  const [chassis, setChassis] = useState("");
  const [bay, setBay] = useState("");
  const [tray, setTray] = useState("");
  const [port, setPort] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    const loc = q.data?.physical_location ?? null;
    setChassis(loc?.chassis ?? "");
    setBay(loc?.bay ?? "");
    setTray(loc?.tray ?? "");
    setPort(loc?.port ?? "");
    setNotes(loc?.notes ?? "");
  }, [q.data]);

  const save = useMutation({
    mutationFn: () =>
      api.setDeviceLocation(deviceId, {
        chassis: chassis || null,
        bay: bay || null,
        tray: tray || null,
        port: port || null,
        notes: notes || null,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["device", deviceId] }),
  });

  const pcieBdf = extractPcieBdf(q.data);

  return (
    <div className="card">
      <h3>Physical location</h3>
      <div className="dim" style={{ fontSize: 12, marginBottom: 12 }}>
        Where to find this drive in the rack. Editable by operators.
      </div>
      {pcieBdf && (
        <div style={{ marginBottom: 12, fontSize: 12 }}>
          <span className="dim">PCIe address (auto-detected): </span>
          <span className="mono">{pcieBdf}</span>
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
        <LabeledInput label="Chassis" value={chassis} onChange={setChassis} placeholder="rack-A" />
        <LabeledInput label="Bay" value={bay} onChange={setBay} placeholder="3" />
        <LabeledInput label="Tray" value={tray} onChange={setTray} placeholder="front-2" />
        <LabeledInput label="Port" value={port} onChange={setPort} placeholder="J1" />
      </div>
      <div style={{ marginTop: 8 }}>
        <label style={{ display: "block", fontSize: 11, color: "#94a3b8" }}>Notes</label>
        <input
          type="text"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="e.g. back of machine, top row"
          style={{ width: "100%", fontSize: 13 }}
        />
      </div>
      <div style={{ marginTop: 12, display: "flex", gap: 8, alignItems: "center" }}>
        <button onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save location"}
        </button>
        {save.isSuccess && <span style={{ color: "#4ade80", fontSize: 12 }}>Saved</span>}
        {save.isError && (
          <span style={{ color: "#f87171", fontSize: 12 }}>
            {(save.error as Error).message}
          </span>
        )}
      </div>
    </div>
  );
}

function LabeledInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  return (
    <div>
      <label style={{ display: "block", fontSize: 11, color: "#94a3b8" }}>{label}</label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        style={{ width: "100%", fontSize: 13 }}
      />
    </div>
  );
}

function extractPcieBdf(device: Device | undefined): string | null {
  if (!device) return null;
  const meta = device.metadata_json as Record<string, unknown> | undefined;
  const pcie = meta?.pcie as Record<string, unknown> | undefined;
  const bdf = pcie?.bdf ?? pcie?.address;
  return typeof bdf === "string" ? bdf : null;
}
