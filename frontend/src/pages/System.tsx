import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api, type EnvironmentCheck, type TuneReceipt } from "@/api";

const STATUS_BADGE: Record<string, string> = {
  pass: "badge-ok",
  warn: "badge-warn",
  fail: "badge-err",
  info: "badge-queued",
};

const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  warning: 1,
  info: 2,
};

export default function System() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["environment"], queryFn: api.getEnvironment });
  const [onlyIssues, setOnlyIssues] = useState(false);

  const meQ = useQuery({ queryKey: ["whoami"], queryFn: api.whoami });
  const isAdmin = meQ.data?.role === "admin" || meQ.data?.is_token;

  const [lastReceipt, setLastReceipt] = useState<TuneReceipt | null>(null);

  const preview = useQuery({
    queryKey: ["tune-preview"],
    queryFn: () => api.tunePreview(),
    enabled: isAdmin,
  });

  const applyMut = useMutation({
    mutationFn: () => api.tuneApply(null),
    onSuccess: (r) => {
      setLastReceipt(r);
      void q.refetch();
      void preview.refetch();
    },
  });

  const revertMut = useMutation({
    mutationFn: () =>
      lastReceipt?.receipt_id
        ? api.tuneRevert(lastReceipt.receipt_id)
        : Promise.reject(new Error("no receipt to revert")),
    onSuccess: (r) => {
      setLastReceipt(r);
      void q.refetch();
      void preview.refetch();
    },
  });

  const grouped = useMemo(() => {
    const groups: Record<string, EnvironmentCheck[]> = {};
    for (const c of q.data?.checks ?? []) {
      if (onlyIssues && c.status !== "warn" && c.status !== "fail") continue;
      (groups[c.category] = groups[c.category] || []).push(c);
    }
    for (const arr of Object.values(groups)) {
      arr.sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9));
    }
    return groups;
  }, [q.data, onlyIssues]);

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <div>
          <h2>{t("system.title")}</h2>
          <div className="dim" style={{ fontSize: 12 }}>{t("system.subtitle")}</div>
        </div>
        <div className="row">
          <label className="dim" style={{ fontSize: 12, alignSelf: "center" }}>
            <input
              type="checkbox"
              checked={onlyIssues}
              onChange={(e) => setOnlyIssues(e.target.checked)}
              style={{ marginRight: 6 }}
            />
            {t("system.onlyIssues")}
          </label>
          <button onClick={() => q.refetch()}>{t("common.refresh")}</button>
        </div>
      </div>

      {q.isLoading ? (
        <div className="dim">{t("common.loading")}</div>
      ) : q.isError ? (
        <div className="card" style={{ background: "#3b1820", border: "1px solid #7f1d1d" }}>
          {String((q.error as Error)?.message ?? q.error)}
        </div>
      ) : !q.data ? (
        <div className="dim">—</div>
      ) : (
        <>
          <div className="row">
            <div className="card stretch">
              <h3>{t("system.total")}</h3>
              <div className="mono" style={{ fontSize: 20 }}>{q.data.summary.total}</div>
            </div>
            <div className="card stretch">
              <h3>{t("system.pass")}</h3>
              <div className="mono" style={{ fontSize: 20, color: "#a7f3d0" }}>
                {q.data.summary.pass}
              </div>
            </div>
            <div className="card stretch">
              <h3>{t("system.warn")}</h3>
              <div className="mono" style={{ fontSize: 20, color: "#fde68a" }}>
                {q.data.summary.warn}
              </div>
            </div>
            <div className="card stretch">
              <h3>{t("system.fail")}</h3>
              <div className="mono" style={{ fontSize: 20, color: "#f87171" }}>
                {q.data.summary.fail}
              </div>
            </div>
            <div className="card stretch">
              <h3>{t("system.info")}</h3>
              <div className="mono" style={{ fontSize: 20, color: "#d4d4d8" }}>
                {q.data.summary.info}
              </div>
            </div>
          </div>

          {isAdmin && (
            <div
              className="card"
              style={{ borderColor: "#78350f", background: "rgba(66, 32, 6, 0.35)" }}
            >
              <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
                <h3 style={{ margin: 0, color: "#fde68a" }}>
                  ⚙ {t("tune.title")}
                </h3>
                <div className="row" style={{ gap: 8 }}>
                  <button
                    className="btn-primary"
                    onClick={() => {
                      if (window.confirm(t("tune.applyConfirm"))) applyMut.mutate();
                    }}
                    disabled={applyMut.isPending}
                  >
                    {applyMut.isPending ? t("common.loading") : t("tune.applyBtn")}
                  </button>
                  <button
                    className="btn-danger"
                    disabled={!lastReceipt || revertMut.isPending}
                    onClick={() => {
                      if (window.confirm(t("tune.revertConfirm"))) revertMut.mutate();
                    }}
                  >
                    {revertMut.isPending ? t("common.loading") : t("tune.revertBtn")}
                  </button>
                </div>
              </div>
              <div className="dim" style={{ fontSize: 11, marginTop: 6, marginBottom: 10 }}>
                {t("tune.help")}
              </div>
              {preview.data && preview.data.preview.length > 0 && (
                <table>
                  <thead>
                    <tr>
                      <th>{t("tune.key")}</th>
                      <th>{t("tune.path")}</th>
                      <th>{t("tune.current")}</th>
                      <th>{t("tune.desired")}</th>
                      <th>{t("tune.change")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.data.preview.map((p, i) => (
                      <tr key={`${p.key}-${i}-${p.path}`}>
                        <td className="mono" style={{ fontSize: 12 }}>{p.key}</td>
                        <td className="mono dim" style={{ fontSize: 11 }}>{p.path ?? "—"}</td>
                        <td className="mono">{p.current ?? "—"}</td>
                        <td className="mono">{p.desired ?? "—"}</td>
                        <td>
                          {p.will_change ? (
                            <span className="badge badge-warn">{t("tune.willChange")}</span>
                          ) : (
                            <span className="badge badge-ok">{t("tune.alreadyOk")}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {lastReceipt && (
                <div style={{ marginTop: 12 }}>
                  <div style={{ fontSize: 12, marginBottom: 6 }}>
                    {lastReceipt.reverted ? t("tune.revertedReceipt") : t("tune.appliedReceipt")}
                  </div>
                  <table>
                    <thead>
                      <tr>
                        <th>{t("tune.key")}</th>
                        <th>{t("tune.path")}</th>
                        <th>{t("tune.before")}</th>
                        <th>{t("tune.after")}</th>
                        <th>{t("tune.ok")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {lastReceipt.results.map((r, i) => (
                        <tr key={`${r.key}-${i}-${r.path}`}>
                          <td className="mono" style={{ fontSize: 12 }}>{r.key}</td>
                          <td className="mono dim" style={{ fontSize: 11 }}>{r.path}</td>
                          <td className="mono">{r.before ?? "—"}</td>
                          <td className="mono">{r.after ?? "—"}</td>
                          <td>
                            <span className={`badge ${r.ok ? "badge-ok" : "badge-err"}`}>
                              {r.ok ? "ok" : "fail"}
                            </span>
                            {r.error && (
                              <span className="dim mono" style={{ fontSize: 10, marginLeft: 6 }}>
                                {r.error}
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {lastReceipt.revert_error && (
                    <div className="badge badge-err" style={{ marginTop: 8 }}>
                      {t("tune.revertError")}: {lastReceipt.revert_error}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {Object.keys(grouped).length === 0 ? (
            <div className="card dim">{t("system.noneInCategory")}</div>
          ) : (
            Object.entries(grouped).map(([cat, checks]) => (
              <div className="card" key={cat}>
                <h3 style={{ textTransform: "uppercase", letterSpacing: "0.5px" }}>{cat}</h3>
                <table>
                  <thead>
                    <tr>
                      <th>{t("system.check")}</th>
                      <th>{t("system.status")}</th>
                      <th>{t("system.value")}</th>
                      <th>{t("system.expected")}</th>
                      <th>{t("system.severity")}</th>
                      <th>{t("system.remediation")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {checks.map((c) => (
                      <tr key={`${cat}-${c.name}`}>
                        <td className="mono">{c.name}</td>
                        <td>
                          <span className={`badge ${STATUS_BADGE[c.status] ?? "badge-queued"}`}>
                            {c.status}
                          </span>
                        </td>
                        <td className="mono" style={{ fontSize: 12 }}>{c.value ?? "—"}</td>
                        <td className="dim" style={{ fontSize: 12 }}>{c.expected ?? "—"}</td>
                        <td className="dim">{c.severity}</td>
                        <td className="mono" style={{ fontSize: 11 }}>
                          {c.remediation ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))
          )}
        </>
      )}
    </div>
  );
}
