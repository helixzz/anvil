import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api, type SsoConfig } from "@/api";

const ROLES = ["viewer", "operator", "admin"];

const EMPTY: SsoConfig = {
  enabled: false,
  idp_metadata_url: "",
  idp_entity_id: "",
  sp_entity_id: "anvil",
  sp_acs_url: "",
  username_attribute: "uid",
  display_name_attribute: "displayName",
  email_attribute: "mail",
  groups_attribute: "memberOf",
  default_role: "viewer",
  mappings: [],
};

export default function Sso() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["sso-config"], queryFn: api.getSsoConfig });

  const [config, setConfig] = useState<SsoConfig>(EMPTY);
  useEffect(() => {
    if (q.data) setConfig(q.data);
  }, [q.data]);

  const saveMut = useMutation({
    mutationFn: (c: SsoConfig) => api.saveSsoConfig(c),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sso-config"] }),
  });

  const [testUser, setTestUser] = useState("");
  const [testGroups, setTestGroups] = useState("");
  const [testResult, setTestResult] = useState<string | null>(null);

  const testMut = useMutation({
    mutationFn: () =>
      api.ssoTestAssertion({
        username: testUser,
        display_name: null,
        groups: testGroups.split(",").map((g) => g.trim()).filter(Boolean),
      }),
    onSuccess: (r) =>
      setTestResult(
        `${t("sso.testOk")}: ${r.user.username} → ${r.user.role} (token truncated: ${r.token.slice(0, 32)}…)`,
      ),
    onError: (err: Error) => setTestResult(`${t("sso.testFail")}: ${err.message}`),
  });

  function updateMapping(i: number, patch: Partial<SsoConfig["mappings"][number]>) {
    setConfig((c) => {
      const next = { ...c, mappings: [...c.mappings] };
      next.mappings[i] = { ...next.mappings[i], ...patch };
      return next;
    });
  }

  function addMapping() {
    setConfig((c) => ({ ...c, mappings: [...c.mappings, { group: "", role: "viewer" }] }));
  }

  function removeMapping(i: number) {
    setConfig((c) => ({ ...c, mappings: c.mappings.filter((_, idx) => idx !== i) }));
  }

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <div>
          <h2>{t("sso.title")}</h2>
          <div className="dim" style={{ fontSize: 12 }}>{t("sso.subtitle")}</div>
        </div>
      </div>

      <div className="card">
        <h3>{t("sso.configSection")}</h3>
        <form
          className="col"
          onSubmit={(e) => {
            e.preventDefault();
            saveMut.mutate(config);
          }}
        >
          <label>
            <input
              type="checkbox"
              checked={config.enabled}
              onChange={(e) => setConfig({ ...config, enabled: e.target.checked })}
            />
            &nbsp;{t("sso.enable")}
          </label>
          <div className="dim" style={{ fontSize: 11, marginBottom: 8 }}>
            {t("sso.enableHelp")}
          </div>

          {[
            ["idp_metadata_url", t("sso.idpMetadataUrl")],
            ["idp_entity_id", t("sso.idpEntityId")],
            ["sp_entity_id", t("sso.spEntityId")],
            ["sp_acs_url", t("sso.spAcsUrl")],
            ["username_attribute", t("sso.usernameAttr")],
            ["display_name_attribute", t("sso.displayNameAttr")],
            ["email_attribute", t("sso.emailAttr")],
            ["groups_attribute", t("sso.groupsAttr")],
          ].map(([field, label]) => (
            <label key={field} style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <span style={{ flex: "0 0 200px", fontSize: 12 }}>{label}</span>
              <input
                style={{ flex: 1 }}
                value={(config as unknown as Record<string, string>)[field] ?? ""}
                onChange={(e) =>
                  setConfig({ ...config, [field]: e.target.value } as SsoConfig)
                }
              />
            </label>
          ))}

          <label style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <span style={{ flex: "0 0 200px", fontSize: 12 }}>{t("sso.defaultRole")}</span>
            <select
              value={config.default_role}
              onChange={(e) => setConfig({ ...config, default_role: e.target.value })}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>

          <div style={{ marginTop: 12 }}>
            <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ margin: 0 }}>{t("sso.mappingSection")}</h3>
              <button type="button" onClick={addMapping}>
                + {t("sso.addMapping")}
              </button>
            </div>
            <div className="dim" style={{ fontSize: 11, margin: "4px 0 8px" }}>
              {t("sso.mappingHelp")}
            </div>
            {config.mappings.length === 0 ? (
              <div className="dim">{t("sso.noMappings")}</div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>{t("sso.idpGroup")}</th>
                    <th>{t("sso.anvilRole")}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {config.mappings.map((m, i) => (
                    <tr key={i}>
                      <td>
                        <input
                          value={m.group}
                          onChange={(e) => updateMapping(i, { group: e.target.value })}
                          placeholder="CN=Anvil Operators,OU=Groups,DC=example,DC=com"
                          style={{ width: "100%" }}
                        />
                      </td>
                      <td>
                        <select
                          value={m.role}
                          onChange={(e) => updateMapping(i, { role: e.target.value })}
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>
                              {r}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <button type="button" className="btn-danger" onClick={() => removeMapping(i)}>
                          {t("common.cancel")}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="row" style={{ marginTop: 12 }}>
            <button type="submit" className="btn-primary" disabled={saveMut.isPending}>
              {saveMut.isPending ? t("common.loading") : t("sso.save")}
            </button>
            {saveMut.isError && (
              <span className="badge badge-err">{(saveMut.error as Error).message}</span>
            )}
            {saveMut.isSuccess && <span className="badge badge-ok">{t("sso.saved")}</span>}
          </div>
        </form>
      </div>

      <div className="card">
        <h3>{t("sso.testSection")}</h3>
        <div className="dim" style={{ fontSize: 11, marginBottom: 8 }}>
          {t("sso.testHelp")}
        </div>
        <div className="row" style={{ gap: 8, alignItems: "center" }}>
          <input
            value={testUser}
            onChange={(e) => setTestUser(e.target.value)}
            placeholder={t("admin.username")}
          />
          <input
            value={testGroups}
            onChange={(e) => setTestGroups(e.target.value)}
            placeholder={t("sso.testGroupsPlaceholder")}
            style={{ minWidth: 360 }}
          />
          <button
            type="button"
            onClick={() => testMut.mutate()}
            disabled={!config.enabled || !testUser || testMut.isPending}
          >
            {testMut.isPending ? t("common.loading") : t("sso.testBtn")}
          </button>
        </div>
        {!config.enabled && (
          <div className="dim" style={{ fontSize: 11, marginTop: 6 }}>
            {t("sso.testDisabledHint")}
          </div>
        )}
        {testResult && (
          <pre className="mono" style={{ whiteSpace: "pre-wrap", fontSize: 11, marginTop: 8 }}>
            {testResult}
          </pre>
        )}
      </div>
    </div>
  );
}
