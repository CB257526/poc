import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { ApiError, formatDateTime, yuan } from "../api/client";
import { Hero, StatusPill } from "../components/ui";
import type { QuoteDetail, Task, TaskStatus } from "../types";
import { TASK_STATUS_LABEL } from "../types";

function detailsOf(task: Task | null): QuoteDetail[] {
  if (!task || task.status !== "completed") return [];
  return task.quote_summary?.details ?? [];
}

function statusKind(status: TaskStatus) {
  if (status === "completed") return "done" as const;
  if (status === "failed") return "bad" as const;
  if (status === "running" || status === "needs_correction") return "warn" as const;
  return "idle" as const;
}

function taskLabel(task: Task) {
  const summary = task.quote_summary;
  const fee = summary ? ` · ${yuan(summary.total_fee)}` : "";
  const count = summary ? ` · ${summary.quote_count} 条` : "";
  return `${formatDateTime(task.created_at)} · ${task.filename}${count}${fee}`;
}

export function QuotesPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskId, setTaskId] = useState("");
  const [error, setError] = useState("");
  const [level, setLevel] = useState("全部");
  const [platform, setPlatform] = useState("全部");
  const [state, setState] = useState("全部");
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
  const details = detailsOf(task);

  const options = useMemo(() => ({
    levels: ["全部", ...Array.from(new Set(details.map((d) => d.media_level).filter(Boolean))).sort()],
    platforms: ["全部", ...Array.from(new Set(details.map((d) => d.platform).filter(Boolean))).sort()],
    statuses: ["全部", ...Array.from(new Set(details.map((d) => d.status).filter(Boolean))).sort()],
  }), [details]);

  const filtered = details.filter((row) =>
    (level === "全部" || row.media_level === level)
    && (platform === "全部" || row.platform === platform)
    && (state === "全部" || row.status === state),
  );

  useEffect(() => {
    setLevel("全部");
    setPlatform("全部");
    setState("全部");
  }, [taskId]);

  if (error) return <div className="alert error">{error}</div>;
  if (!loaded) return <p>加载中…</p>;

  const completed = task?.status === "completed";

  return (
    <>
      <Hero title="约稿资料" subtitle="选择任意一次处理记录，查看并筛选该次约稿明细" />
      {tasks.length ? (
        <div className="panel">
          <h2>处理记录</h2>
          <p style={{ color: "var(--muted)" }}>共 {tasks.length} 次处理。切换批次后下方明细会跟着变。</p>
          <div className="filters">
            <label className="field" style={{ minWidth: 360, flex: 1 }}>
              处理批次
              <select
                value={taskId}
                onChange={(e) => setTaskId(e.target.value)}
              >
                {tasks.map((item) => (
                  <option key={item.task_id} value={item.task_id}>
                    {TASK_STATUS_LABEL[item.status]} · {taskLabel(item)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {task ? (
            <p style={{ color: "var(--muted)", marginBottom: 0 }}>
              任务 ID：{task.task_id}
              {" · "}
              <StatusPill kind={statusKind(task.status)}>{TASK_STATUS_LABEL[task.status]}</StatusPill>
              {task.quote_summary
                ? ` · 媒体 ${task.quote_summary.media_count} · 约稿 ${task.quote_summary.quote_count} · ${yuan(task.quote_summary.total_fee)}`
                : null}
            </p>
          ) : null}
        </div>
      ) : (
        <div className="alert info">尚无任务。请先在「数据处理」上传链接表。</div>
      )}

      {task && completed && details.length ? (
        <div className="alert success">正在展示该次处理的可入账约稿明细。</div>
      ) : task && completed ? (
        <div className="alert info">该次任务已完成，但没有可入账的约稿记录。</div>
      ) : task ? (
        <div className="alert info">
          该次任务「{TASK_STATUS_LABEL[task.status]}」，完成后才会生成约稿明细。
        </div>
      ) : null}

      {details.length ? (
        <>
          <div className="filters">
            <label className="field">
              媒体等级
              <select value={level} onChange={(e) => setLevel(e.target.value)}>
                {options.levels.map((item) => <option key={item}>{item}</option>)}
              </select>
            </label>
            <label className="field">
              发布平台
              <select value={platform} onChange={(e) => setPlatform(e.target.value)}>
                {options.platforms.map((item) => <option key={item}>{item}</option>)}
              </select>
            </label>
            <label className="field">
              状态
              <select value={state} onChange={(e) => setState(e.target.value)}>
                {options.statuses.map((item) => <option key={item}>{item}</option>)}
              </select>
            </label>
          </div>
          <div className="panel">
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>媒体名称</th>
                    <th>发布平台</th>
                    <th>类型</th>
                    <th>媒体等级</th>
                    <th>粉丝量</th>
                    <th>约稿数量</th>
                    <th>金额</th>
                    <th>状态</th>
                    <th>标题</th>
                    <th>发布日期</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((row, index) => (
                    <tr key={`${row.media_name}-${row.publish_url}-${index}`}>
                      <td>{row.media_name}</td>
                      <td>{row.platform}</td>
                      <td>{row.content_type}</td>
                      <td>{row.media_level}</td>
                      <td>{row.followers}</td>
                      <td>{row.quote_count}</td>
                      <td>{yuan(row.amount)}</td>
                      <td>{row.status}</td>
                      <td>{row.title}</td>
                      <td>{row.publish_date}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p style={{ color: "var(--muted)" }}>当前显示 {filtered.length} 条约稿记录。</p>
          </div>
        </>
      ) : null}
    </>
  );
}
