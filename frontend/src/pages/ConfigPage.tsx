import { useEffect, useState } from "react";
import { api } from "../api";
import { ApiError, formatDateTime } from "../api/client";
import { Hero, StatusPill } from "../components/ui";
import type { ConfigKind, ConfigStatus } from "../types";

const KINDS: { kind: ConfigKind; filename: string }[] = [
  { kind: "media_library", filename: "3-媒体库.xlsx" },
  { kind: "accounts", filename: "4-账户信息.xlsx" },
  { kind: "fee_rules", filename: "5-费用.xlsx" },
];

export function ConfigPage() {
  const [status, setStatus] = useState<ConfigStatus | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<ConfigKind | "">("");

  useEffect(() => {
    api.configStatus()
      .then(setStatus)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "加载失败"));
  }, []);

  async function upload(kind: ConfigKind, file: File | undefined) {
    if (!file) return;
    setBusy(kind);
    setError("");
    try {
      const next = await api.uploadConfig(kind, file);
      setStatus(next);
      setMessage(`${file.name} 已保存`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "上传失败");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <Hero title="基础配置" subtitle="管理员维护媒体库、账户信息和费用规则。约稿资料与付款表由工作流按固定模板生成，不必上传。" />
      {error ? <div className="alert error">{error}</div> : null}
      {message ? <div className="alert success">{message}</div> : null}
      <div className="panel">
        <h2>配置文件</h2>
        <p style={{ color: "var(--muted)" }}>只需配置表 3 / 4 / 5。业务人员日常只上传链接表。</p>
        {(status?.files ?? []).map((item) => {
          const hint = KINDS.find((k) => k.kind === item.kind);
          return (
            <div className="file-row" key={item.kind}>
              <div>
                <b>{item.label}</b>
                <div style={{ color: "var(--muted)", fontSize: 13 }}>
                  {item.filename || hint?.filename} · 更新于 {formatDateTime(item.updated_at)}
                </div>
              </div>
              <span style={{ display: "flex", gap: 10, alignItems: "center" }}>
                {item.configured ? <StatusPill kind="done">已配置</StatusPill> : <StatusPill kind="warn">未配置</StatusPill>}
                <label className="btn">
                  {busy === item.kind ? "上传中…" : "更新文件"}
                  <input
                    type="file"
                    accept=".xlsx"
                    hidden
                    disabled={busy === item.kind}
                    onChange={(e) => void upload(item.kind, e.target.files?.[0])}
                  />
                </label>
              </span>
            </div>
          );
        })}
      </div>
    </>
  );
}
