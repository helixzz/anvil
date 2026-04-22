import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";

import { api, clearToken, getToken, setToken } from "@/api";
import Dashboard from "@/pages/Dashboard";
import Devices from "@/pages/Devices";
import DeviceDetail from "@/pages/DeviceDetail";
import Runs from "@/pages/Runs";
import NewRun from "@/pages/NewRun";
import RunDetail from "@/pages/RunDetail";
import Models from "@/pages/Models";
import ModelDetail from "@/pages/ModelDetail";
import Compare from "@/pages/Compare";
import System from "@/pages/System";
import Users from "@/pages/Users";
import Sso from "@/pages/Sso";

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
  const [mode, setMode] = useState<"login" | "token">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [tokenValue, setTokenValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submitLogin(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await api.login(username, password);
      setToken(res.token);
      onAuth();
    } catch (err) {
      clearToken();
      setError((err as Error).message);
    }
  }

  async function submitToken(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!tokenValue) return;
    setToken(tokenValue);
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
        <div className="row" style={{ gap: 8, marginBottom: 12 }}>
          <button
            className={mode === "login" ? "btn-primary" : ""}
            onClick={() => setMode("login")}
          >
            {t("auth.modeLogin")}
          </button>
          <button
            className={mode === "token" ? "btn-primary" : ""}
            onClick={() => setMode("token")}
          >
            {t("auth.modeToken")}
          </button>
        </div>
        {mode === "login" ? (
          <form onSubmit={submitLogin} className="col">
            <p className="dim" style={{ fontSize: 12 }}>{t("auth.loginHelp")}</p>
            <input
              type="text"
              autoComplete="username"
              value={username}
              placeholder={t("auth.usernamePlaceholder")}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
            />
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              placeholder={t("auth.passwordPlaceholder")}
              onChange={(e) => setPassword(e.target.value)}
            />
            <button type="submit" className="btn-primary">
              {t("auth.submitLogin")}
            </button>
            {error && <div className="badge badge-err">{error}</div>}
          </form>
        ) : (
          <form onSubmit={submitToken} className="col">
            <p className="dim" style={{ fontSize: 12 }}>{t("auth.description")}</p>
            <input
              type="password"
              value={tokenValue}
              placeholder={t("auth.tokenPlaceholder")}
              onChange={(e) => setTokenValue(e.target.value)}
              autoFocus
            />
            <button type="submit" className="btn-primary">
              {t("auth.submit")}
            </button>
            {error && <div className="badge badge-err">{error}</div>}
          </form>
        )}
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

  const meQuery = useQuery({
    queryKey: ["whoami"],
    queryFn: api.whoami,
    enabled: authenticated,
  });
  const isAdmin = meQuery.data?.role === "admin" || meQuery.data?.is_token;

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
        <NavLink to="/compare">{t("nav.compare")}</NavLink>
        <NavLink to="/system">{t("nav.system")}</NavLink>
        {isAdmin && <NavLink to="/admin/users">{t("nav.users")}</NavLink>}
        {isAdmin && <NavLink to="/admin/sso">{t("nav.sso")}</NavLink>}
        <NavLink to="/runs/new">{t("nav.newRun")}</NavLink>
        <div style={{ marginTop: "auto", paddingTop: 16 }} className="col">
          <div className="dim" style={{ fontSize: 12 }}>
            {t("status.version")}:&nbsp;
            <span className="mono" title="API version">
              api&nbsp;{statusQuery.data?.version ?? "—"}
            </span>
            &nbsp;·&nbsp;
            <span className="mono" title="Web UI version">
              web&nbsp;{__ANVIL_WEB_VERSION__}
            </span>
          </div>
          {meQuery.data && (
            <div className="dim" style={{ fontSize: 12 }}>
              {t("auth.signedInAs")}:&nbsp;
              <span className="mono">{meQuery.data.username}</span>
              &nbsp;
              <span className={`badge ${meQuery.data.role === "admin" ? "badge-err" : meQuery.data.role === "operator" ? "badge-warn" : "badge"}`}>
                {meQuery.data.role}
              </span>
            </div>
          )}
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
          <Route path="/devices/:id" element={<DeviceDetail />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="/runs/new" element={<NewRun />} />
          <Route path="/runs/:id" element={<RunDetail />} />
          <Route path="/models" element={<Models />} />
          <Route path="/models/:slug" element={<ModelDetail />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/system" element={<System />} />
          {isAdmin && <Route path="/admin/users" element={<Users />} /> }
          {isAdmin && <Route path="/admin/sso" element={<Sso />} /> }
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
