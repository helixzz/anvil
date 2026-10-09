import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import dayjs from "dayjs";

import { api, type RunnerOut } from "@/api";
import { humanBytes } from "@/lib/format";

function StatusBadge({ runner }: { runner: RunnerOut }) {
  const { t } = useTranslation();
  if (!runner.enabled) {
    return <span className="badge badge-queued">{t("runners.disabled")}</span>;
  }
  if (runner.busy) {
    return <span className="badge badge-running">{t("runners.busy")}</span>;
  }
  if (runner.online) {
    return <span className="badge badge-ok">{t("runners.online")}</span>;
  }
  return <span className="badge badge-err">{t("runners.offline")}</span>;
}

function shortFingerprint(fp: string | null): string {
  if (!fp) return "—";
  return fp.length > 16 ? `${fp.slice(0, 16)}…` : fp;
}

export default function Runners() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["runners"], queryFn: api.listRunners });
  const meQ = useQuery({ queryKey: ["whoami"], queryFn: api.whoami });
  const isAdmin = meQ.data?.role === "admin" || meQ.data?.is_token;

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [token, setTokenValue] = useState("");
  const [fingerprint, setFingerprint] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pinned, setPinned] = useState<{ name: string; fingerprint: string } | null>(null);

  const createMut = useMutation({
    mutationFn: () =>
      api.createRunner({
        name,
        address,
        token,
        tls_fingerprint: fingerprint.trim() ? fingerprint.trim() : null,
      }),
    onSuccess: (r) => {
      setShowForm(false);
      setName("");
      setAddress("");
      setTokenValue("");
      setFingerprint("");
      setError(null);
      if (r.tls_fingerprint) {
        setPinned({ name: r.name, fingerprint: r.tls_fingerprint });
      }
      qc.invalidateQueries({ queryKey: ["runners"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const updateMut = useMutation({
    mutationFn: (p: { id: string; body: Parameters<typeof api.updateRunner>[1] }) =>
      api.updateRunner(p.id, p.body),
    onSuccess: (r) => {
      if (r.tls_fingerprint) {
        setPinned({ name: r.name, fingerprint: r.tls_fingerprint });
      }
      qc.invalidateQueries({ queryKey: ["runners"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteRunner(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runners"] }),
    onError: (err: Error) => setError(err.message),
  });

  function rotateToken(r: RunnerOut) {
    const next = window.prompt(t("runners.rotateTokenPrompt", { name: r.name }));
    if (next == null || next.length < 16) return;
    updateMut.mutate({ id: r.id, body: { token: next } });
  }

  function repin(r: RunnerOut) {
    if (!window.confirm(t("runners.repinConfirm", { name: r.name }))) return;
    updateMut.mutate({ id: r.id, body: { refetch_fingerprint: true } });
  }

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <div>
          <h2>{t("runners.title")}</h2>
          <div className="dim" style={{ fontSize: 12, maxWidth: 720 }}>
            {t("runners.subtitle")}
          </div>
        </div>
        {isAdmin && (
          <button className="btn-primary" onClick={() => { setShowForm((v) => !v); setError(null); }}>
            {t("runners.addRunner")}
          </button>
        )}
      </div>

      {pinned && (
        <div className="card" style={{ borderColor: "#78350f", background: "rgba(66, 32, 6, 0.35)" }}>
          <h3 style={{ margin: 0, color: "#fde68a" }}>{t("runners.pinnedTitle")}</h3>
          <div className="dim" style={{ fontSize: 12, marginTop: 6 }}>
            {t("runners.pinnedHelp")}
          </div>
          <div className="mono" style={{ fontSize: 13, marginTop: 8, wordBreak: "break-all" }}>
            {pinned.name}: {pinned.fingerprint}
          </div>
          <div style={{ marginTop: 8 }}>
            <button onClick={() => setPinned(null)} style={{ fontSize: 12 }}>
              OK
            </button>
          </div>
        </div>
      )}

      {isAdmin && showForm && (
        <div className="card">
          <h3>{t("runners.addRunner")}</h3>
          <form
            className="col"
            onSubmit={(e) => {
              e.preventDefault();
              if (!name || !address || token.length < 16) return;
              createMut.mutate();
            }}
          >
            <div className="row">
              <input
                value={name}
                placeholder={t("runners.name")}
                onChange={(e) => setName(e.target.value)}
              />
              <input
                value={address}
                placeholder={t("runners.addressPlaceholder")}
                onChange={(e) => setAddress(e.target.value)}
              />
              <input
                type="password"
                value={token}
                placeholder={t("runners.tokenPlaceholder")}
                onChange={(e) => setTokenValue(e.target.value)}
              />
              <input
                value={fingerprint}
                placeholder={t("runners.fingerprintOptional")}
                onChange={(e) => setFingerprint(e.target.value)}
              />
              <button type="submit" className="btn-primary" disabled={createMut.isPending}>
                {createMut.isPending ? t("common.loading") : t("runners.createBtn")}
              </button>
              <button type="button" onClick={() => setShowForm(false)}>
                {t("common.cancel")}
              </button>
            </div>
          </form>
        </div>
      )}

      {error && <div className="badge badge-err" style={{ padding: 8 }}>{error}</div>}

      {q.isLoading ? (
        <div className="dim">{t("common.loading")}</div>
      ) : !q.data || q.data.length === 0 ? (
        <div className="card dim">{t("runners.noRunners")}</div>
      ) : (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>{t("runners.name")}</th>
                <th>{t("runners.status")}</th>
                <th>{t("runners.address")}</th>
                <th>{t("runners.host")}</th>
                <th>{t("runners.version")}</th>
                <th>{t("runners.devices")}</th>
                <th>{t("runners.lastSeen")}</th>
                <th>{t("runners.fingerprint")}</th>
                {isAdmin && <th />}
              </tr>
            </thead>
            <tbody>
              {q.data.map((r) => {
                const hi = r.host_info;
                return (
                  <tr key={r.id}>
                    <td>
                      <span className="mono">{r.name}</span>{" "}
                      {r.kind === "unix" && (
                        <span className="badge">{t("runners.localKind")}</span>
                      )}
                      {r.error && !r.online && (
                        <div className="dim" style={{ fontSize: 11, color: "var(--danger)" }}>
                          {r.error}
                        </div>
                      )}
                    </td>
                    <td>
                      <StatusBadge runner={r} />
                    </td>
                    <td className="mono" style={{ fontSize: 12 }}>{r.address}</td>
                    <td>
                      {hi ? (
                        <>
                          <div style={{ fontSize: 12 }}>{hi.hostname ?? "—"}</div>
                          <div className="dim" style={{ fontSize: 11 }}>
                            {[
                              hi.cpu_model,
                              hi.cpu_count != null ? t("runners.cores", { count: hi.cpu_count }) : null,
                              hi.mem_total_bytes != null ? humanBytes(hi.mem_total_bytes) : null,
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </div>
                        </>
                      ) : (
                        <span className="dim">—</span>
                      )}
                    </td>
                    <td className="mono" style={{ fontSize: 12 }}>
                      {hi?.runner_version ?? "—"}
                    </td>
                    <td className="mono">{r.device_count}</td>
                    <td className="dim" style={{ fontSize: 11 }}>
                      {r.last_seen_at ? dayjs(r.last_seen_at).format("YYYY-MM-DD HH:mm") : "—"}
                    </td>
                    <td className="mono" style={{ fontSize: 11 }} title={r.tls_fingerprint ?? undefined}>
                      {shortFingerprint(r.tls_fingerprint)}
                    </td>
                    {isAdmin && (
                      <td style={{ whiteSpace: "nowrap" }}>
                        <button
                          onClick={() => updateMut.mutate({ id: r.id, body: { enabled: !r.enabled } })}
                          disabled={updateMut.isPending}
                          style={{ fontSize: 12 }}
                        >
                          {r.enabled ? t("runners.disable") : t("runners.enable")}
                        </button>
                        {r.kind === "tcp" && (
                          <>
                            <button
                              onClick={() => rotateToken(r)}
                              disabled={updateMut.isPending}
                              style={{ fontSize: 12, marginLeft: 4 }}
                            >
                              {t("runners.rotateToken")}
                            </button>
                            <button
                              onClick={() => repin(r)}
                              disabled={updateMut.isPending}
                              style={{ fontSize: 12, marginLeft: 4 }}
                            >
                              {t("runners.repin")}
                            </button>
                          </>
                        )}
                        {r.id !== "local" && (
                          <button
                            className="btn-danger"
                            onClick={() => {
                              if (window.confirm(t("runners.deleteConfirm", { name: r.name }))) {
                                deleteMut.mutate(r.id);
                              }
                            }}
                            disabled={deleteMut.isPending}
                            style={{ fontSize: 12, marginLeft: 4 }}
                          >
                            {t("runners.delete")}
                          </button>
                        )}
                      </td>
                    )}
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
