import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { ApiError, yuan } from "../api/client";
import { Hero, StatusPill } from "../components/ui";
import type { ConfigStatus, MediaRecord, Task, TaskStatus, ValidateTaskResponse } from "../types";
import { TASK_STATUS_LABEL } from "../types";

function statusKind(status: TaskStatus): "done" | "warn" | "bad" | "idle" {
  if (status === "completed") return "done";
  if (status === "failed") return "bad";
  if (status === "needs_correction" || status === "running") return "warn";
  return "idle";
}

export function ProcessingPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [config, setConfig] = useState<ConfigStatus | null>(null);
  const [validate, setValidate] = useState<ValidateTaskResponse | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const [task, setTask] = useState<Task | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.configStatus().then(setConfig).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!task || task.status !== "running") return;
    const timer = window.setInterval(() => {
      void api.getTask(task.task_id).then(setTask);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [task]);

  const unmatched = useMemo(
    () => (validate?.records ?? []).filter((row) => row.match_status === "unmatched"),
    [validate],
  );

  async function start() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const payload = await api.validateTask(file);
      setValidate(payload);
      setNames(Object.fromEntries(payload.records.map((row) => [String(row.row_number), row.media_name])));
      if (payload.status === "ready") {
        await api.runTask(payload.task_id);
        setTask(await api.getTask(payload.task_id));
        setMessage("输入预检通过，节点 1—6 已开始执行。");
      } else {
        setMessage(`输入预检暂停：发现 ${payload.records.filter((r) => r.match_status === "unmatched").length} 个媒体名称无法匹配媒体库。`);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "处理失败");
    } finally {
      setBusy(false);
    }
  }

  async function recorrect() {
    if (!validate) return;
    setBusy(true);
    setError("");
    try {
      const payload = await api.submitCorrections(validate.task_id, names);
      setValidate(payload);
      if (payload.status === "ready") {
        await api.runTask(payload.task_id);
        setTask(await api.getTask(payload.task_id));
        setMessage("媒体名称重新校验通过，节点 1—6 已继续执行。");
      } else {
        setError(`仍有 ${payload.records.filter((r) => r.match_status === "unmatched").length} 个媒体名称未匹配，请继续修改。`);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "重新校验失败");
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setValidate(null);
    setTask(null);
    setNames({});
    setMessage("");
    setError("");
    setFile(null);
    if (fileRef.current) fileRef.current.value = "";
  }

  const progress = task ? task.progress.completed_nodes.length / task.progress.total_nodes : 0;

  return (
    <>
      <Hero title="数据处理" subtitle="上传本次链接表，系统自动生成约稿资料、费用汇总和付款文件" />
      <div className="panel">
        <h2>本次任务文件</h2>
        <p style={{ color: "var(--muted)" }}>业务人员每次只需上传链接表。未选择文件时，演示模式会用一条媒体名有误的模拟数据。</p>
        <label className="field">
          1-链接.xlsx
          <input ref={fileRef} type="file" accept=".xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
      </div>
      <div className="panel">
        <h3>基础配置状态</h3>
        <div className="grid-3">
          {(config?.files ?? []).map((item) => (
            <div key={item.kind}>
              {item.configured ? <StatusPill kind="done">{item.label} · 已配置</StatusPill> : <StatusPill kind="warn">{item.label} · 未配置</StatusPill>}
            </div>
          ))}
        </div>
      </div>
      <button className="btn primary" disabled={busy} onClick={() => void start()}>
        {busy ? "处理中…" : "开始自动处理  →"}
      </button>
      {message ? <div className="alert info">{message}</div> : null}
      {error ? <div className="alert error">{error}</div> : null}

      {validate && unmatched.length > 0 && task?.status !== "running" && task?.status !== "completed" ? (
        <div className="panel">
          <h2>媒体名称修正</h2>
          <p>系统尚未执行链接抓取和费用计算。主题、原表行号和链接信息仅用于定位，不能修改。</p>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>原表行号</th>
                  <th>主题</th>
                  <th>媒体名称（可修改）</th>
                  <th>链接数量</th>
                  <th>链接预览</th>
                  <th>校验状态</th>
                  <th>建议修改为</th>
                </tr>
              </thead>
              <tbody>
                {validate.records.map((row: MediaRecord) => (
                  <tr key={row.record_id} className={row.match_status === "unmatched" ? "mismatch" : undefined}>
                    <td>{row.row_number}</td>
                    <td>{row.topic}</td>
                    <td>
                      <select
                        value={names[String(row.row_number)] ?? row.media_name}
                        onChange={(e) => setNames((prev) => ({ ...prev, [String(row.row_number)]: e.target.value }))}
                      >
                        {!validate.allowed_media_names.includes(names[String(row.row_number)] ?? row.media_name) ? (
                          <option value={row.media_name}>{row.media_name}（当前值）</option>
                        ) : null}
                        {validate.allowed_media_names.map((name) => (
                          <option key={name} value={name}>{name}</option>
                        ))}
                      </select>
                    </td>
                    <td>{row.link_count}</td>
                    <td>{row.link_preview}</td>
                    <td>{(names[String(row.row_number)] ?? row.media_name) && validate.allowed_media_names.includes(names[String(row.row_number)] ?? row.media_name) ? "✓ 已匹配" : "未匹配"}</td>
                    <td>{row.suggested_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: "flex", gap: 12, marginTop: 16 }}>
            <button className="btn primary" disabled={busy} onClick={() => void recorrect()}>重新校验并继续处理</button>
            <button className="btn ghost" onClick={reset}>取消本次处理</button>
          </div>
        </div>
      ) : null}

      {task?.status === "running" ? (
        <div className="panel">
          <h2>后台处理中</h2>
          <p>后端正在执行链接抓取、媒体与账户匹配、费用计算和文件生成。</p>
          <div className="progress"><span style={{ width: `${Math.min(progress, 1) * 100}%` }} /></div>
          <p>已完成 {task.progress.completed_nodes.length}/{task.progress.total_nodes} 个处理节点</p>
        </div>
      ) : null}

      {task?.status === "failed" ? <div className="alert error">后端处理失败：{task.error || "请查看任务问题详情"}</div> : null}

      {task?.status === "completed" ? (
        <div className="alert success">
          最近一次任务已完成（{TASK_STATUS_LABEL[task.status]}）。可前往约稿资料、费用分析和文件输出查看结果。
          {task.quote_summary ? ` 费用合计 ${yuan(task.quote_summary.total_fee)}。` : null}
        </div>
      ) : null}

      {task ? (
        <p style={{ color: "var(--muted)" }}>
          任务 ID：{task.task_id} · <StatusPill kind={statusKind(task.status)}>{TASK_STATUS_LABEL[task.status]}</StatusPill>
        </p>
      ) : null}
    </>
  );
}
