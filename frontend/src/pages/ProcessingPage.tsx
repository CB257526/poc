import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { errorMessage, yuan } from "../api/client";
import { Hero, IssueList, StatusPill } from "../components/ui";
import type { ConfigStatus, MediaRecord, Task, TaskIssue, TaskStatus, ValidateTaskResponse } from "../types";
import { TASK_STATUS_LABEL } from "../types";

function statusKind(status: TaskStatus): "done" | "warn" | "bad" | "idle" {
  if (status === "completed") return "done";
  if (status === "failed") return "bad";
  if (status === "needs_correction" || status === "running") return "warn";
  return "idle";
}

function sortIssues(issues: TaskIssue[]) {
  const rank = { critical: 0, error: 1, warning: 2 };
  return [...issues].sort((a, b) => (rank[a.severity] ?? 9) - (rank[b.severity] ?? 9));
}

function describeValidateBlockers(payload: ValidateTaskResponse) {
  const unmatched = payload.records.filter((row) => row.match_status === "unmatched").length;
  const invalidUrls = payload.issues.filter((issue) => issue.code === "INVALID_URL").length;
  const parts: string[] = [];
  if (unmatched) parts.push(`${unmatched} 个媒体名称无法匹配媒体库`);
  if (invalidUrls) parts.push(`${invalidUrls} 条链接不符合规范（如 ww、全角小数点）`);
  if (!parts.length) parts.push("存在输入错误");
  return parts.join("，") + "。";
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
    api.configStatus()
      .then(setConfig)
      .catch((err: unknown) => setError(errorMessage(err, "无法加载配置状态")));
    api.latestTask()
      .then((latest) => {
        if (latest && ["running", "completed", "failed", "needs_correction", "ready"].includes(latest.status)) {
          setTask(latest);
        }
      })
      .catch((err: unknown) => setError(errorMessage(err, "无法加载最近任务")));
  }, []);

  useEffect(() => {
    if (!task || task.status !== "running") return;
    const timer = window.setInterval(() => {
      void api.getTask(task.task_id)
        .then(setTask)
        .catch((err: unknown) => setError(errorMessage(err, "轮询任务状态失败")));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [task]);

  const unmatched = useMemo(
    () => (validate?.records ?? []).filter((row) => row.match_status === "unmatched"),
    [validate],
  );
  const invalidUrlIssues = useMemo(
    () => (validate?.issues ?? []).filter((issue) => issue.code === "INVALID_URL"),
    [validate],
  );

  const displayIssues = useMemo(() => {
    const source = (task?.issues?.length ? task.issues : validate?.issues) ?? [];
    return sortIssues(source);
  }, [task, validate]);

  async function start() {
    if (!file) {
      setError("请先选择 1-链接.xlsx");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    setTask(null);
    try {
      const payload = await api.validateTask(file);
      setValidate(payload);
      setNames(Object.fromEntries(payload.records.map((row) => [String(row.row_number), row.media_name])));
      if (payload.status === "ready") {
        await api.runTask(payload.task_id);
        setTask(await api.getTask(payload.task_id));
        setMessage("输入预检通过，节点 1—6 已开始执行。");
      } else {
        setMessage(`输入预检暂停：${describeValidateBlockers(payload)}`);
      }
    } catch (err) {
      setError(errorMessage(err, "处理失败"));
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
        setError(`仍未通过预检：${describeValidateBlockers(payload)}`);
      }
    } catch (err) {
      setError(errorMessage(err, "重新校验失败"));
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

  const progress = task && task.progress.total_nodes
    ? task.progress.completed_nodes.length / task.progress.total_nodes
    : 0;

  const warningCount = displayIssues.filter((item) => item.severity === "warning").length;
  const blockingCount = displayIssues.length - warningCount;

  return (
    <>
      <Hero title="数据处理" subtitle="上传本次链接表，系统自动生成约稿资料、费用汇总和付款文件" />
      <div className="panel">
        <h2>本次任务文件</h2>
        <p style={{ color: "var(--muted)" }}>业务人员每次只需上传链接表。媒体名称修正不会改写原始 Excel。</p>
        <label className="field">
          1-链接.xlsx
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        {file ? <p style={{ color: "var(--muted)", marginTop: 8 }}>已选择：{file.name}</p> : null}
      </div>
      <div className="panel">
        <h3>基础配置状态</h3>
        <div className="grid-3">
          {(config?.files ?? []).map((item) => (
            <div key={item.kind}>
              {item.configured
                ? <StatusPill kind="done">{item.label} · 已配置</StatusPill>
                : <StatusPill kind="warn">{item.label} · 未配置</StatusPill>}
            </div>
          ))}
        </div>
        {config && !config.all_ready ? (
          <p className="alert warn">基础配置未齐，预检可能失败。请管理员先到「基础配置」上传媒体库、账户和费用表。</p>
        ) : null}
      </div>
      <button className="btn primary" disabled={busy || !file} onClick={() => void start()}>
        {busy ? "处理中…" : "开始自动处理  →"}
      </button>
      {message ? <div className="alert info">{message}</div> : null}
      {error ? <div className="alert error">{error}</div> : null}

      {validate && invalidUrlIssues.length > 0 && unmatched.length === 0 && task?.status !== "running" && task?.status !== "completed" ? (
        <div className="panel">
          <h2>链接格式错误</h2>
          <p>表1 中的原始链接需符合 URL 规范（半角小数点、完整 www 等）。系统不会自动改写，请修正 Excel 后重新上传。</p>
          <button className="btn ghost" onClick={reset}>取消本次处理并重新上传</button>
        </div>
      ) : null}

      {validate && unmatched.length > 0 && task?.status !== "running" && task?.status !== "completed" ? (
        <div className="panel">
          <h2>媒体名称修正</h2>
          <p>系统尚未执行链接抓取和费用计算。请手动填写媒体库中的标准媒体名，提交后由后端重新校验。</p>
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
                {validate.records.map((row: MediaRecord) => {
                  const current = names[String(row.row_number)] ?? row.media_name;
                  const matched = validate.allowed_media_names.includes(current);
                  return (
                    <tr key={row.record_id} className={matched ? undefined : "mismatch"}>
                      <td>{row.row_number}</td>
                      <td>{row.topic}</td>
                      <td>
                        <input
                          type="text"
                          value={current}
                          onChange={(e) => setNames((prev) => ({ ...prev, [String(row.row_number)]: e.target.value }))}
                          placeholder="请输入媒体库中的标准媒体名"
                          aria-label={`第 ${row.row_number} 行媒体名称`}
                        />
                      </td>
                      <td>{row.link_count}</td>
                      <td>{row.link_preview}</td>
                      <td>{matched ? "✓ 已匹配" : "未匹配"}</td>
                      <td>{row.suggested_name}</td>
                    </tr>
                  );
                })}
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

      {task?.status === "failed" ? (
        <div className="alert error">
          本次处理未完成，请根据下方提示修正数据后重新处理；仍无法处理时请联系技术人员。
        </div>
      ) : null}

      {task?.status === "completed" && blockingCount ? (
        <div className="alert warn">
          任务已完成，但仍有 {blockingCount} 条错误未入账
          {warningCount ? `、${warningCount} 条警告` : ""}。明细见下方问题列表。
        </div>
      ) : null}

      {task?.status === "completed" && !blockingCount ? (
        <div className="alert success">
          最近一次任务已完成（{TASK_STATUS_LABEL[task.status]}）。可前往约稿资料、费用分析和文件输出查看结果。
          {task.quote_summary ? ` 费用合计 ${yuan(task.quote_summary.total_fee)}。` : null}
          {warningCount ? ` 另有 ${warningCount} 条警告。` : null}
        </div>
      ) : null}

      <IssueList issues={displayIssues} />

      {task ? (
        <p style={{ color: "var(--muted)" }}>
          任务 ID：{task.task_id} · <StatusPill kind={statusKind(task.status)}>{TASK_STATUS_LABEL[task.status]}</StatusPill>
        </p>
      ) : null}
    </>
  );
}
