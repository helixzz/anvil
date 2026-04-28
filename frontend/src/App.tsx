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
import AuditLog from "@/pages/AuditLog";
import Schedules from "@/pages/Schedules";
import Inventory from "@/pages/Inventory";

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
  const [mode, setMode] = useState<"sso" | "login" | "token">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [tokenValue, setTokenValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  const ssoQ = useQuery({
    queryKey: ["sso-status"],
    queryFn: api.ssoStatus,
    staleTime: 60000,
  });
  const ssoEnabled = ssoQ.data?.enabled === true;

  useEffect(() => {
    if (ssoEnabled && mode === "login" && !username && !password) {
      setMode("sso");
    }
  }, [ssoEnabled, mode, username, password]);

  function handleSsoLogin() {
    window.location.href = "/api/auth/sso/login?return_to=" + encodeURIComponent(window.location.pathname || "/");
  }

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

        {ssoEnabled && mode === "sso" && (
          <div className="col" style={{ gap: 12, alignItems: "center" }}>
            <button className="btn-primary" onClick={handleSsoLogin} style={{ padding: "12px 32px", fontSize: 15 }}>
              Sign in with SSO
            </button>
            <button
              className="dim"
              onClick={() => setMode("login")}
              style={{ fontSize: 12, textDecoration: "underline", background: "none", border: "none", cursor: "pointer" }}
            >
              or use a local account
            </button>
          </div>
        )}

        {(!ssoEnabled || mode !== "sso") && (
          <>
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
              {ssoEnabled && (
                <button
                  className="dim"
                  onClick={() => setMode("sso")}
                  style={{ fontSize: 12 }}
                >
                  SSO
                </button>
              )}
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
          </>
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
  const navigate = useNavigate();
  const [authenticated, setAuthenticated] = useState<boolean>(() => {
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get("token");
    if (urlToken) {
      setToken(urlToken);
      const cleanUrl = window.location.pathname;
      window.history.replaceState({}, "", cleanUrl);
      return true;
    }
    return !!getToken();
  });

  const [theme, setTheme] = useState<"dark" | "light">(() => {
    const stored = localStorage.getItem("anvil-theme");
    return stored === "light" ? "light" : "dark";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("anvil-theme", theme);
  }, [theme]);

  function toggleTheme() {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  }

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

        <div className="nav-group">
          <div className="nav-group-label">Monitor</div>
          <NavLink to="/" end>{t("nav.dashboard")}</NavLink>
          <NavLink to="/system">{t("nav.system")}</NavLink>
          {isAdmin && <NavLink to="/admin/audit-log">Audit log</NavLink>}
        </div>

        <div className="nav-group">
          <div className="nav-group-label">Inventory</div>
            <NavLink to="/devices">{t("nav.devices")}</NavLink>
            <NavLink to="/models">{t("nav.models")}</NavLink>
            <NavLink to="/inventory">Inventory</NavLink>
        </div>

        <div className="nav-group">
          <div className="nav-group-label">Benchmark</div>
          <NavLink to="/runs">{t("nav.runs")}</NavLink>
          <NavLink to="/runs/new">{t("nav.newRun")}</NavLink>
          <NavLink to="/compare">{t("nav.compare")}</NavLink>
        </div>

        {isAdmin && (
          <div className="nav-group">
            <div className="nav-group-label">Access</div>
            <NavLink to="/admin/users">{t("nav.users")}</NavLink>
            <NavLink to="/admin/sso">{t("nav.sso")}</NavLink>
            <NavLink to="/admin/schedules">Schedules</NavLink>
          </div>
        )}

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
          <div className="row" style={{ gap: 4, alignItems: "center" }}>
            <LanguageSwitcher />
            <button onClick={toggleTheme} title="Toggle dark/light theme" style={{ fontSize: 13, padding: "4px 8px" }}>
              {theme === "dark" ? "☀" : "☾"}
            </button>
          </div>
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
          <Route path="/inventory" element={<Inventory />} />
          {isAdmin && <Route path="/admin/users" element={<Users />} /> }
          {isAdmin && <Route path="/admin/sso" element={<Sso />} /> }
          {isAdmin && <Route path="/admin/audit-log" element={<AuditLog />} /> }
          {isAdmin && <Route path="/admin/schedules" element={<Schedules />} /> }
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
