import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { api, type Device } from "@/api";

export default function Inventory() {
  const q = useQuery({ queryKey: ["devices"], queryFn: api.listDevices });

  const grouped = useMemo(() => {
    const chassis: Record<string, Device[]> = {};
    for (const d of q.data ?? []) {
      const loc = d.physical_location;
      const key = loc?.chassis || "Unassigned";
      if (!chassis[key]) chassis[key] = [];
      chassis[key].push(d);
    }
    return chassis;
  }, [q.data]);

  if (q.isLoading) return <div className="dim">Loading…</div>;

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <div>
          <h2>Inventory</h2>
          <div className="dim" style={{ fontSize: 12 }}>
            Physical layout of every device. Edit location from Device Detail.
          </div>
        </div>
      </div>

      {Object.keys(grouped).length === 0 ? (
        <div className="card dim" style={{ textAlign: "center", padding: 40 }}>
          No devices have a physical location assigned. Go to a device and set its chassis/bay to populate this view.
        </div>
      ) : (
        Object.entries(grouped).map(([chassisName, devices]) => (
          <div key={chassisName} className="card">
            <h3>{chassisName} ({devices.length} drives)</h3>
            <BayGrid devices={devices} />
          </div>
        ))
      )}
    </div>
  );
}

function BayGrid({ devices }: { devices: Device[] }) {
  const bays = useMemo(() => {
    const map = new Map<string, Device>();
    for (const d of devices) {
      const bay = d.physical_location?.bay;
      if (bay) map.set(String(bay), d);
    }
    const max = Math.max(1, ...Array.from(map.keys()).map(Number).filter((n) => !isNaN(n)));
    const rows: (Device | null)[][] = [];
    const cols = 8;
    for (let i = 0; i < max; i += cols) {
      rows.push(Array.from({ length: cols }, (_, j) => map.get(String(i + j + 1)) || null));
    }
    return rows;
  }, [devices]);

  const unassigned = devices.filter((d) => !d.physical_location?.bay);

  return (
    <div>
      <table style={{ width: "auto" }}>
        <tbody>
          {bays.map((row, ri) => (
            <tr key={ri}>
              {row.map((d, ci) => (
                <td key={ci} style={{ padding: 4, border: "1px solid var(--border)", minWidth: 100, verticalAlign: "top" }}>
                  {d ? (
                    <Link to={`/devices/${d.id}`} style={{ textDecoration: "none" }}>
                      <div className="mono" style={{ fontSize: 11, fontWeight: 600 }}>{d.brand} {d.model}</div>
                      <div className="dim mono" style={{ fontSize: 10 }}>{d.serial}</div>
                      <div className="dim" style={{ fontSize: 10 }}>{d.protocol}</div>
                    </Link>
                  ) : (
                    <div className="dim" style={{ fontSize: 11, textAlign: "center", padding: "12px 0" }}>
                      {ri * 8 + ci + 1}
                    </div>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {unassigned.length > 0 && (
        <div className="dim" style={{ marginTop: 8, fontSize: 11 }}>
          {unassigned.length} drive(s) without bay assignment: {unassigned.map((d) => d.serial).join(", ")}
        </div>
      )}
    </div>
  );
}
