import { useEffect, useState } from "react";
import { api } from "../api";
import { ApiError, formatDateTime } from "../api/client";
import { Hero, StatusPill } from "../components/ui";
import { ROLE_LABEL, STATUS_LABEL, type Role, type User, type UserStatus } from "../types";

function statusKind(status: UserStatus): "done" | "warn" | "bad" | "idle" {
  if (status === "active") return "done";
  if (status === "pending") return "warn";
  return "bad";
}

export function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function reload() {
    setUsers(await api.listUsers());
  }

  useEffect(() => {
    reload().catch((err: unknown) => setError(err instanceof ApiError ? err.message : "加载失败"));
  }, []);

  async function patch(id: string, next: { role?: Role; status?: UserStatus }) {
    setError("");
    try {
      await api.updateUser(id, next);
      await reload();
      setMessage("用户信息已更新");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "更新失败");
    }
  }

  return (
    <>
      <Hero title="用户管理" subtitle="审核注册申请、分配角色、启用或停用账号" />
      {error ? <div className="alert error">{error}</div> : null}
      {message ? <div className="alert success">{message}</div> : null}
      <div className="panel">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>姓名</th>
                <th>邮箱</th>
                <th>角色</th>
                <th>状态</th>
                <th>注册时间</th>
                <th>最近登录</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>{user.name}</td>
                  <td>{user.email}</td>
                  <td>
                    <select value={user.role} onChange={(e) => void patch(user.id, { role: e.target.value as Role })}>
                      {(Object.keys(ROLE_LABEL) as Role[]).map((role) => (
                        <option key={role} value={role}>{ROLE_LABEL[role]}</option>
                      ))}
                    </select>
                  </td>
                  <td><StatusPill kind={statusKind(user.status)}>{STATUS_LABEL[user.status]}</StatusPill></td>
                  <td>{formatDateTime(user.created_at)}</td>
                  <td>{formatDateTime(user.last_login_at)}</td>
                  <td style={{ display: "flex", gap: 8 }}>
                    {user.status === "pending" ? (
                      <button className="btn primary" onClick={() => void patch(user.id, { status: "active" })}>通过</button>
                    ) : null}
                    {user.status === "active" ? (
                      <button className="btn danger" onClick={() => void patch(user.id, { status: "disabled" })}>停用</button>
                    ) : null}
                    {user.status === "disabled" ? (
                      <button className="btn" onClick={() => void patch(user.id, { status: "active" })}>启用</button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
