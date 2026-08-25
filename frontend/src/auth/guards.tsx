import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function RequireAuth() {
  const { user, loading } = useAuth();
  if (loading) return <div className="auth-page"><div className="auth-card">正在校验登录状态…</div></div>;
  if (!user) return <Navigate to="/login" replace />;
  return <Outlet />;
}

export function GuestOnly() {
  const { user, loading } = useAuth();
  if (loading) return <div className="auth-page"><div className="auth-card">加载中…</div></div>;
  if (user) return <Navigate to="/" replace />;
  return <Outlet />;
}
