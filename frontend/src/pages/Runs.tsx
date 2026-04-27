import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import dayjs from "dayjs";

import { api } from "@/api";

const PAGE = 25;

const badgeFor: Record<string, string> = {
  complete: "badge-ok",
  failed: "badge-err",
  aborted: "badge-err",
  running: "badge-running",
  preflight: "badge-running",
  queued: "badge-queued",
};

const STATUSES = ["queued", "preflight", "running", "complete", "failed", "aborted"];

export default function Runs() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [profileFilter, setProfileFilter] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const q = useQuery({
    queryKey: ["runs", offset, statusFilter, profileFilter],
    queryFn: () =>
      api.listRuns({
        offset,
        limit: PAGE,
        status: statusFilter || undefined,
        profile_name: profileFilter || undefined,
      }),
    refetchInterval: 2000,
  });

  const delMut = useMutation({
    mutationFn: (ids: string[]) => api.batchDeleteRuns(ids),
    onSuccess: () => {
      setSelected(new Set());
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
  });

  const items = q.data?.items ?? [];
  const total = q.data?.total ?? 0;

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function selectAll() {
    if (selected.size === items.length) setSelected(new Set());
    else setSelected(new Set(items.map((r) => r.id)));
  }

  function prevPage() { setOffset(Math.max(0, offset - PAGE)); setSelected(new Set()); }
  function nextPage() { setOffset(offset + PAGE); setSelected(new Set()); }

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <h2>{t("runs.title")}</h2>
        <Link to="/runs/new">
          <button className="btn-primary">+ {t("nav.newRun")}</button>
        </Link>
      </div>

      <div className="card">
        <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "end" }}>
          <label className="col" style={{ gap: 2 }}>
            <span className="dim" style={{ fontSize: 11 }}>Status</span>
            <select
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value); setOffset(0); setSelected(new Set()); }}
              style={{ fontSize: 12 }}
            >
              <option value="">all</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>{t(`status_labels.${s}` as const, s)}</option>
              ))}
            </select>
          </label>
          <label className="col" style={{ gap: 2 }}>
            <span className="dim" style={{ fontSize: 11 }}>Profile</span>
            <input
              type="text"
              value={profileFilter}
              onChange={(e) => { setProfileFilter(e.target.value); setOffset(0); setSelected(new Set()); }}
              placeholder="e.g. snia_quick_pts"
              style={{ width: 160, fontSize: 12 }}
            />
          </label>
          {selected.size > 0 && (
            <button
              className="btn-danger"
              onClick={() => {
                const ids = Array.from(selected);
                if (window.confirm(`Delete ${ids.length} run(s)?`)) delMut.mutate(ids);
              }}
              disabled={delMut.isPending}
              style={{ fontSize: 12 }}
            >
              {delMut.isPending ? "…" : `Delete ${selected.size}`}
            </button>
          )}
        </div>
      </div>

      {q.isLoading ? (
        <div className="dim">{t("common.loading")}</div>
      ) : items.length === 0 ? (
        <div className="card dim">{t("runs.noRuns")}</div>
      ) : (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th style={{ width: 30 }}>
                  <input type="checkbox" checked={selected.size === items.length && items.length > 0} onChange={selectAll} />
                </th>
                <th>{t("runs.device")}</th>
                <th>{t("runs.profile")}</th>
                <th>{t("runs.status")}</th>
                <th>{t("runs.queuedAt")}</th>
                <th>{t("runs.startedAt")}</th>
                <th>{t("runs.finishedAt")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id}>
                  <td>
                    <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} />
                  </td>
                  <td>
                    <div className="mono">{r.device_model}</div>
                    <div className="dim mono" style={{ fontSize: 11 }}>{r.device_serial}</div>
                  </td>
                  <td>{r.profile_name}</td>
                  <td>
                    <span className={`badge ${badgeFor[r.status] ?? "badge-queued"}`}>
                      {t(`status_labels.${r.status}` as const, r.status)}
                    </span>
                  </td>
                  <td className="dim">{dayjs(r.queued_at).format("HH:mm:ss")}</td>
                  <td className="dim">{r.started_at ? dayjs(r.started_at).format("HH:mm:ss") : "—"}</td>
                  <td className="dim">{r.finished_at ? dayjs(r.finished_at).format("HH:mm:ss") : "—"}</td>
                  <td>
                    <Link to={`/runs/${r.id}`}>{t("runs.viewReport")} →</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="row" style={{ justifyContent: "space-between", marginTop: 12, fontSize: 12 }}>
            <button onClick={prevPage} disabled={offset === 0}>
              ← Previous
            </button>
            <span className="dim">
              {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
            </span>
            <button onClick={nextPage} disabled={offset + PAGE >= total}>
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
