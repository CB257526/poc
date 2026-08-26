import { useEffect, useState } from "react";
import { api } from "../api";
import { ApiError, downloadBlob, formatDateTime, yuan } from "../api/client";
import { Hero, StatusPill } from "../components/ui";
import type { Task } from "../types";
import { TASK_STATUS_LABEL } from "../types";

export function ExportsPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskId, setTaskId] = useState("");
  const [error, setError] = useState("");
  const [busyKey, setBusyKey] = useState("");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api.listTasks()
      .then((items) => {
        setTasks(items);
        const preferred = items.find((item) => item.status === "completed") ?? items[0];
        setTaskId(preferred?.task_id ?? "");
      })
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "加载失败"))
      .finally(() => setLoaded(true));
  }, []);

  const task = tasks.find((item) => item.task_id === taskId) ?? null;
  const ready = task?.status === "completed" && (task.files ?? []).some((file) => file.ready);

  function taskLabel(item: Task) {
    const summary = item.quote_summary;
    const count = summary ? ` · ${summary.quote_count} 条` : "";
    const fee = summary ? ` · ${yuan(summary.total_fee)}` : "";
    return `${formatDateTime(item.created_at)} · ${item.filename}${count}${fee}`;
  }

  async function download(fileKey: string, filename: string) {
    if (!task) return;
    setBusyKey(fileKey);
    setError("");
    try {
      const blob = await api.downloadFile(task.task_id, fileKey);
      downloadBlob(blob, filename);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "下载失败");
    } finally {
      setBusyKey("");
    }
  }

  async function downloadZip() {
    if (!task) return;
    setBusyKey("archive");
    try {
      const blob = await api.downloadAll(task.task_id);
      downloadBlob(blob, "约稿费用验收_处理结果.zip");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "打包下载失败");
    } finally {
      setBusyKey("");
    }
  }

  return (
    <>
      <Hero title="文件输出" subtitle="下载处理结果文件或一次性打包全部结果" />
      {error ? <div className="alert error">{error}</div> : null}
      {!loaded ? <p>加载中…</p> : null}
      {tasks.length ? (
        <div className="panel">
          <h2>处理记录</h2>
          <p style={{ color: "var(--muted)" }}>选择处理批次后，下方会展示该批次生成的文件。</p>
          <label className="field">
            处理批次
            <select
              value={taskId}
              onChange={(event) => {
                setTaskId(event.target.value);
                setBusyKey("");
                setError("");
              }}
            >
              {tasks.map((item) => (
                <option key={item.task_id} value={item.task_id}>
                  {TASK_STATUS_LABEL[item.status]} · {taskLabel(item)}
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : loaded ? (
        <div className="alert info">尚无处理记录。请先在「数据处理」上传链接表。</div>
      ) : null}
      <div className="panel">
        <h2>处理结果文件</h2>
        {ready ? (
          task!.files.map((file) => (
            <div className="file-row" key={file.key}>
              <span>✓ &nbsp; {file.filename}</span>
              <span style={{ display: "flex", gap: 10, alignItems: "center" }}>
                <StatusPill kind={file.ready ? "done" : "warn"}>{file.ready ? "已生成" : "未生成"}</StatusPill>
                <button
                  className="btn primary"
                  disabled={!file.ready || busyKey === file.key}
                  onClick={() => void download(file.key, file.filename)}
                >
                  {busyKey === file.key ? "下载中…" : "下载"}
                </button>
              </span>
            </div>
          ))
        ) : (
          <p className="empty">
            {task
              ? `所选任务「${TASK_STATUS_LABEL[task.status]}」，完成后可下载约稿资料和付款文件。`
              : "尚无已完成任务。请先在「数据处理」上传链接表。"}
          </p>
        )}
      </div>
      {ready ? (
        <button className="btn primary" disabled={busyKey === "archive"} onClick={() => void downloadZip()}>
          {busyKey === "archive" ? "打包中…" : "下载全部结果（ZIP）"}
        </button>
      ) : null}
    </>
  );
}
