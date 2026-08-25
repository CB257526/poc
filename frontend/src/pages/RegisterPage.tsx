import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export function RegisterPage() {
  const { register } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const text = await register({ name, email, password });
      setMessage(text);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "注册失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>申请账号</h1>
        <p className="lead">注册后默认为业务人员，需管理员审核通过才能登录</p>
        {message ? (
          <div className="alert success">{message}</div>
        ) : (
          <form onSubmit={(e) => void onSubmit(e)}>
            <label className="field">
              姓名
              <input value={name} onChange={(e) => setName(e.target.value)} required />
            </label>
            <label className="field">
              企业邮箱
              <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
            </label>
            <label className="field">
              密码（至少 8 位）
              <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" minLength={8} required />
            </label>
            {error ? <div className="alert error">{error}</div> : null}
            <button className="btn primary" disabled={submitting} type="submit">
              {submitting ? "提交中…" : "提交注册"}
            </button>
          </form>
        )}
        <div className="switch-auth">
          已有账号？<Link to="/login">返回登录</Link>
        </div>
      </div>
    </div>
  );
}
