import { useEffect, useState } from "react";
import { api } from "../api";
import { ApiError, downloadBlob } from "../api/client";
import { Hero, StatusPill } from "../components/ui";
import type { Task } from "../types";

export function ExportsPage() {
  const [task, setTask] = useState<Task | null>(null);
  const [error, setError] = useState("");
  const [busyKey, setBusyKey] = useState("");

  useEffect(() => {
    api.latestTask()
      .then(setTask)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "加载失败"));
  }, []);

  const ready = task?.status === "completed" && (task.files?.length ?? 0) > 0;

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
      <div className="panel">
        <h2>处理结果文件</h2>
        {ready ? (
          task!.files.map((file) => (
            <div className="file-row" key={file.key}>
              <span>✓ &nbsp; {file.filename}</span>
              <span style={{ display: "flex", gap: 10, alignItems: "center" }}>
                <StatusPill kind="done">后端已生成</StatusPill>
                <button className="btn primary" disabled={busyKey === file.key} onClick={() => void download(file.key, file.filename)}>
                  {busyKey === file.key ? "下载中…" : "下载"}
                </button>
              </span>
            </div>
          ))
        ) : (
          <>
            <p style={{ color: "var(--muted)" }}>当前显示演示结果；上传真实文件并等待任务完成后，将自动切换为真实文件。</p>
            {["2-约稿资料_完成版.xlsx", "6-付款.xlsx"].map((name) => (
              <div className="file-row" key={name}>
                <span>✓ &nbsp; {name}</span>
                <StatusPill kind="done">演示文件</StatusPill>
              </div>
            ))}
          </>
        )}
      </div>
      {task ? (
        <button className="btn primary" disabled={!ready || busyKey === "archive"} onClick={() => void downloadZip()}>
          {busyKey === "archive" ? "打包中…" : "下载全部结果（ZIP）"}
        </button>
      ) : null}
    </>
  );
}
