import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import dayjs from "dayjs";
import { api, type AnvilUser } from "@/api";

const ROLES: AnvilUser["role"][] = ["viewer", "operator", "admin"];

function RoleBadge({ role }: { role: AnvilUser["role"] }) {
  const cls =
    role === "admin" ? "badge-err" : role === "operator" ? "badge-warn" : "badge";
  return <span className={`badge ${cls}`}>{role}</span>;
}

export default function Users() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const users = useQuery({ queryKey: ["admin-users"], queryFn: api.adminListUsers });

  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newRole, setNewRole] = useState<AnvilUser["role"]>("viewer");
  const [error, setError] = useState<string | null>(null);

  const createMut = useMutation({
    mutationFn: () =>
      api.adminCreateUser({
        username: newUsername,
        password: newPassword,
        display_name: newDisplayName || undefined,
        role: newRole,
      }),
    onSuccess: () => {
      setNewUsername("");
      setNewPassword("");
      setNewDisplayName("");
      setNewRole("viewer");
      setError(null);
      qc.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const updateMut = useMutation({
    mutationFn: (p: { id: string; body: Parameters<typeof api.adminUpdateUser>[1] }) =>
      api.adminUpdateUser(p.id, p.body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
    onError: (err: Error) => setError(err.message),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.adminDeleteUser(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
    onError: (err: Error) => setError(err.message),
  });

  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="topbar">
        <div>
          <h2>{t("admin.usersTitle")}</h2>
          <div className="dim" style={{ fontSize: 12 }}>{t("admin.usersSubtitle")}</div>
        </div>
      </div>

      <div className="card">
        <h3>{t("admin.createUser")}</h3>
        <form
          className="col"
          onSubmit={(e) => {
            e.preventDefault();
            if (!newUsername || !newPassword) return;
            createMut.mutate();
          }}
        >
          <div className="row">
            <input
              value={newUsername}
              placeholder={t("admin.username")}
              onChange={(e) => setNewUsername(e.target.value)}
            />
            <input
              type="password"
              value={newPassword}
              placeholder={t("admin.password")}
              onChange={(e) => setNewPassword(e.target.value)}
            />
            <input
              value={newDisplayName}
              placeholder={t("admin.displayName")}
              onChange={(e) => setNewDisplayName(e.target.value)}
            />
            <select value={newRole} onChange={(e) => setNewRole(e.target.value as AnvilUser["role"])}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            <button type="submit" className="btn-primary" disabled={createMut.isPending}>
              {t("admin.createUserBtn")}
            </button>
          </div>
          {error && <div className="badge badge-err" style={{ marginTop: 8 }}>{error}</div>}
        </form>
      </div>

      <div className="card">
        <h3>{t("admin.existingUsers")}</h3>
        {users.isLoading ? (
          <div className="dim">{t("common.loading")}</div>
        ) : !users.data || users.data.length === 0 ? (
          <div className="dim">{t("admin.noUsers")}</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>{t("admin.username")}</th>
                <th>{t("admin.displayName")}</th>
                <th>{t("admin.role")}</th>
                <th>{t("admin.active")}</th>
                <th>{t("admin.lastLogin")}</th>
                <th>{t("admin.created")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {users.data.map((u) => (
                <tr key={u.id}>
                  <td className="mono">{u.username}</td>
                  <td>{u.display_name ?? "—"}</td>
                  <td>
                    <select
                      value={u.role}
                      onChange={(e) =>
                        updateMut.mutate({ id: u.id, body: { role: e.target.value } })
                      }
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>
                    <span style={{ marginLeft: 6 }}>
                      <RoleBadge role={u.role} />
                    </span>
                  </td>
                  <td>
                    <label>
                      <input
                        type="checkbox"
                        checked={u.is_active}
                        onChange={(e) =>
                          updateMut.mutate({
                            id: u.id,
                            body: { is_active: e.target.checked },
                          })
                        }
                      />
                      &nbsp;{u.is_active ? t("admin.yes") : t("admin.no")}
                    </label>
                  </td>
                  <td className="dim">
                    {u.last_login_at ? dayjs(u.last_login_at).format("YYYY-MM-DD HH:mm") : "—"}
                  </td>
                  <td className="dim">{dayjs(u.created_at).format("YYYY-MM-DD")}</td>
                  <td>
                    <button
                      className="btn-danger"
                      onClick={() => {
                        if (window.confirm(t("admin.deleteConfirm", { username: u.username }))) {
                          deleteMut.mutate(u.id);
                        }
                      }}
                    >
                      {t("admin.delete")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
