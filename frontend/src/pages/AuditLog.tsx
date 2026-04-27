import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import dayjs from "dayjs";

import { api } from "@/api";

const PAGE_SIZE = 100;

export default function AuditLog() {
  const { t } = useTranslation();
  const [before, setBefore] = useState<string | null>(null);
  const [actionFilter, setActionFilter] = useState<string>("");
  const [actorFilter, setActorFilter] = useState<string>("");
  const [stack, setStack] = useState<string[]>([]);

  const q = useQuery({
    queryKey: ["audit-log", before, actionFilter, actorFilter],
    queryFn: () =>
      api.adminAuditLog({
        limit: PAGE_SIZE,
        before: before ?? undefined,
        action: actionFilter || undefined,
        actor: actorFilter || undefined,
      }),
  });

  const items = q.data?.items ?? [];
  const actions = q.data?.actions ?? [];

  useEffect(() => {
    if (before !== null && stack.length > 0 && stack[stack.length - 1] !== before) {
      setStack((s) => [...s, before]);
    }
  }, [before, stack]);

  function goNext() {
    if (q.data?.next_before != null) {
      setBefore(String(q.data.next_before));
    }
  }

  function goPrev() {
    const s = [...stack];
    s.pop();
    setStack(s);
    setBefore(s.length > 0 ? s[s.length - 1] : null);
  }

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <div>
          <h2>Audit log</h2>
          <div className="dim" style={{ fontSize: 12 }}>
            Every privileged action (login, role change, SSO config, env tune) on this Anvil instance.
          </div>
        </div>
      </div>

      <div className="card">
        <div className="row" style={{ gap: 12, flexWrap: "wrap", alignItems: "end" }}>
          <FilterSelect
            label="Action"
            value={actionFilter}
            onChange={(v) => { setActionFilter(v); setBefore(null); setStack([]); }}
            options={actions}
            placeholder="all"
          />
          <label className="col" style={{ gap: 4 }}>
            <span className="dim" style={{ fontSize: 11 }}>
              Actor
            </span>
            <input
              type="text"
              value={actorFilter}
              onChange={(e) => {
                setActorFilter(e.target.value);
                setBefore(null);
                setStack([]);
              }}
              placeholder="e.g. admin"
              style={{ width: 180, fontSize: 12 }}
            />
          </label>
        </div>
      </div>

      {q.isLoading ? (
        <div className="dim">{t("common.loading")}</div>
      ) : q.isError ? (
        <div className="card" style={{ background: "#3b1820", border: "1px solid #7f1d1d" }}>
          {String((q.error as Error)?.message ?? q.error)}
        </div>
      ) : items.length === 0 ? (
        <div className="card dim" style={{ textAlign: "center", padding: 40 }}>
          No audit log entries match the current filter.
        </div>
      ) : (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th style={{ width: 160 }}>Timestamp</th>
                <th style={{ width: 140 }}>Actor</th>
                <th style={{ width: 180 }}>Action</th>
                <th style={{ width: 250 }}>Target</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.id}>
                  <td className="dim mono" style={{ fontSize: 11 }}>
                    {row.ts ? dayjs(row.ts).format("YYYY-MM-DD HH:mm:ss") : "—"}
                  </td>
                  <td className="mono" style={{ fontSize: 12 }}>
                    {row.actor || "—"}
                  </td>
                  <td className="mono" style={{ fontSize: 12 }}>
                    {row.action}
                  </td>
                  <td className="mono dim" style={{ fontSize: 11 }}>
                    {row.target || "—"}
                  </td>
                  <td>
                    <pre
                      className="mono dim"
                      style={{ fontSize: 10, maxHeight: 60, overflow: "auto", margin: 0 }}
                    >
                      {row.details ? JSON.stringify(row.details, null, 2) : "—"}
                    </pre>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div
            className="row"
            style={{ justifyContent: "space-between", marginTop: 12, fontSize: 12 }}
          >
            <button onClick={goPrev} disabled={stack.length === 0}>
              ← Previous
            </button>
            <span className="dim">
              {items.length} of {q.data?.has_more ? "many" : items.length} entries
            </span>
            <button onClick={goNext} disabled={!q.data?.has_more}>
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  placeholder: string;
}) {
  return (
    <label className="col" style={{ gap: 4 }}>
      <span className="dim" style={{ fontSize: 11 }}>
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{ fontSize: 12 }}
      >
        <option value="">{placeholder}</option>
        {options.map((a) => (
          <option key={a} value={a}>
            {a}
          </option>
        ))}
      </select>
    </label>
  );
}
