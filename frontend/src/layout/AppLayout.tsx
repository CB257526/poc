import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { PAGE_ROLES, ROLE_LABEL, type Role } from "../types";

const NAV = [
  { to: "/", label: "首页概览" },
  { to: "/processing", label: "数据处理" },
  { to: "/quotes", label: "约稿资料" },
  { to: "/analytics", label: "费用分析" },
  { to: "/exceptions", label: "异常提醒" },
  { to: "/exports", label: "文件输出" },
  { to: "/config", label: "基础配置" },
  { to: "/users", label: "用户管理" },
];

function canSee(path: string, role: Role) {
  return (PAGE_ROLES[path] ?? []).includes(role);
}

export function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  if (!user) return null;

  const visible = NAV.filter((item) => canSee(item.to, user.role));
  const blocked = PAGE_ROLES[location.pathname] && !canSee(location.pathname, user.role);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <h1>约稿平台</h1>
          <p>媒体约稿 · 费用验收</p>
        </div>
        <nav className="nav">
          <span className="group">业务</span>
          {visible.filter((item) => !["/config", "/users"].includes(item.to)).map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"}>
              {item.label}
            </NavLink>
          ))}
          {visible.some((item) => ["/config", "/users"].includes(item.to)) && (
            <>
              <span className="group">管理</span>
              {visible.filter((item) => ["/config", "/users"].includes(item.to)).map((item) => (
                <NavLink key={item.to} to={item.to}>{item.label}</NavLink>
              ))}
            </>
          )}
        </nav>
        <div className="sidebar-user">
          <div>{user.name}</div>
          <div className="role">{ROLE_LABEL[user.role]} · {user.email}</div>
          <button type="button" onClick={() => void logout().then(() => navigate("/login"))}>退出登录</button>
        </div>
      </aside>
      <main className="main">
        {blocked ? (
          <div className="panel">
            <h2>无访问权限</h2>
            <p>当前角色「{ROLE_LABEL[user.role]}」不能访问此页面。如需开通，请联系管理员。</p>
          </div>
        ) : (
          <Outlet />
        )}
      </main>
    </div>
  );
}
