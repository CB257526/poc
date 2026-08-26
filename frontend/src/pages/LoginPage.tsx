import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const SEED_PASSWORD = "Passw0rd!";

export function LoginPage() {
  const { login, error } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("operator@byd.local");
  const [password, setPassword] = useState(SEED_PASSWORD);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/");
    } catch {
      /* shown via auth.error */
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>约稿平台</h1>
        <p className="lead">登录后处理链接表、查看费用与导出付款文件</p>
        <form onSubmit={(e) => void onSubmit(e)}>
          <label className="field">
            邮箱
            <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required autoComplete="username" />
          </label>
          <label className="field">
            密码
            <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" required autoComplete="current-password" />
          </label>
          {error ? <div className="alert error">{error}</div> : null}
          <button className="btn primary" disabled={submitting} type="submit">
            {submitting ? "登录中…" : "登录"}
          </button>
        </form>
        <div className="switch-auth">
          还没有账号？<Link to="/register">申请注册</Link>
        </div>
        <div className="demo-accounts">
          种子账号（密码均为 <code>{SEED_PASSWORD}</code>）
          <br />admin@byd.local 管理员
          <br />operator@byd.local 业务人员
          <br />finance@byd.local 财务
          <br />viewer@byd.local 只读
        </div>
      </div>
    </div>
  );
}
