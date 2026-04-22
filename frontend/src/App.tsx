import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";

import { api, clearToken, getToken, setToken } from "@/api";
import Dashboard from "@/pages/Dashboard";
import Devices from "@/pages/Devices";
import Runs from "@/pages/Runs";
import NewRun from "@/pages/NewRun";
import RunDetail from "@/pages/RunDetail";
import Models from "@/pages/Models";
import ModelDetail from "@/pages/ModelDetail";

function LanguageSwitcher() {
  const { i18n } = useTranslation();
  const next = i18n.language?.startsWith("zh") ? "en" : "zh";
  return (
    <button onClick={() => void i18n.changeLanguage(next)}>
      {i18n.language?.startsWith("zh") ? "English" : "中文"}
    </button>
  );
}

function TokenGate({ onAuth }: { onAuth: () => void }) {
  const { t } = useTranslation();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!value) return;
    setToken(value);
    try {
      await api.status();
      onAuth();
    } catch (err) {
      clearToken();
      setError((err as Error).message);
    }
  }

  return (
    <div className="token-gate">
      <div className="card">
        <h2>{t("auth.title")}</h2>
        <p className="dim">{t("auth.description")}</p>
        <form onSubmit={submit} className="col">
          <input
            type="password"
            value={value}
            placeholder={t("auth.tokenPlaceholder")}
            onChange={(e) => setValue(e.target.value)}
            autoFocus
          />
          <button type="submit" className="btn-primary">
            {t("auth.submit")}
          </button>
          {error && <div className="badge badge-err">{error}</div>}
        </form>
      </div>
      <div style={{ textAlign: "center" }}>
        <LanguageSwitcher />
      </div>
    </div>
  );
}

export default function App() {
  const { t } = useTranslation();
  const [authenticated, setAuthenticated] = useState<boolean>(!!getToken());
  const navigate = useNavigate();

  useEffect(() => {
    const handler = () => setAuthenticated(false);
    window.addEventListener("anvil:auth-required", handler);
    return () => window.removeEventListener("anvil:auth-required", handler);
  }, []);

  const statusQuery = useQuery({
    queryKey: ["status"],
    queryFn: api.status,
    enabled: authenticated,
    refetchInterval: 5000,
  });

  if (!authenticated) {
    return <TokenGate onAuth={() => setAuthenticated(true)} />;
  }

  function signOut() {
    clearToken();
    setAuthenticated(false);
    navigate("/");
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>
          <span style={{ color: "var(--accent)" }}>■</span> {t("app.name")}
        </h1>
        <NavLink to="/" end>
          {t("nav.dashboard")}
        </NavLink>
        <NavLink to="/devices">{t("nav.devices")}</NavLink>
        <NavLink to="/runs">{t("nav.runs")}</NavLink>
        <NavLink to="/models">{t("nav.models")}</NavLink>
        <NavLink to="/runs/new">{t("nav.newRun")}</NavLink>
        <div style={{ marginTop: "auto", paddingTop: 16 }} className="col">
          <div className="dim" style={{ fontSize: 12 }}>
            {t("status.version")}:&nbsp;
            <span className="mono">{statusQuery.data?.version ?? "—"}</span>
          </div>
          <div className="dim" style={{ fontSize: 12 }}>
            {t("status.runner")}:&nbsp;
            <span
              className={
                statusQuery.data?.runner_connected ? "badge badge-ok" : "badge badge-err"
              }
            >
              {statusQuery.data?.runner_connected
                ? t("status.runnerConnected")
                : t("status.runnerDisconnected")}
            </span>
          </div>
          {statusQuery.data?.simulation_mode && (
            <div className="badge badge-warn">{t("status.simulation")}</div>
          )}
          <LanguageSwitcher />
          <button onClick={signOut}>{t("common.signOut")}</button>
        </div>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/devices" element={<Devices />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="/runs/new" element={<NewRun />} />
          <Route path="/runs/:id" element={<RunDetail />} />
          <Route path="/models" element={<Models />} />
          <Route path="/models/:slug" element={<ModelDetail />} />
          <Route
            path="*"
            element={
              <div>
                <h2>404</h2>
                <Link to="/">Home</Link>
              </div>
            }
          />
        </Routes>
      </main>
    </div>
  );
}
