import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { errorMessage, formatDateTime, yuan } from "../api/client";
import { Hero, IssueList, StatusPill } from "../components/ui";
import type { QuoteDetail, Task, TaskIssue, TaskStatus } from "../types";
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
  const [saving, setSaving] = useState(false);
  const [correctionMessage, setCorrectionMessage] = useState("");
  const [publicationCorrections, setPublicationCorrections] = useState<
    Record<string, { title: string; article_type: string }>
  >({});

  useEffect(() => {
    api.listTasks()
      .then((items) => {
        setTasks(items);
        const preferred = items.find((item) => item.status === "completed") ?? items[0];
        setTaskId(preferred?.task_id ?? "");
      })
      .catch((err: unknown) => setError(errorMessage(err, "加载失败")))
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

  useEffect(() => {
    if (!task || task.status !== "running") return;
    const timer = window.setInterval(() => {
      void api.getTask(task.task_id)
        .then((updated) => setTasks((items) => items.map((item) => (
          item.task_id === updated.task_id ? updated : item
        ))))
        .catch((err: unknown) => setError(errorMessage(err, "刷新处理状态失败")));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [task]);

  if (!loaded && !error) return <p>加载中…</p>;

  const completed = task?.status === "completed";
  const issues = task?.issues ?? [];
  const editableRecords = Array.from(new Map(
    issues
      .filter((issue) => ["SCRAPE_FAILED", "MISSING_TITLE", "MISSING_ARTICLE_TYPE"].includes(issue.code) && issue.record_id)
      .map((issue) => [issue.record_id as string, issue]),
  ).values());

  function updatePublicationCorrection(
    issue: TaskIssue,
    field: "title" | "article_type",
    value: string,
  ) {
    if (!issue.record_id) return;
    setPublicationCorrections((current) => ({
      ...current,
      [issue.record_id as string]: {
        title: current[issue.record_id as string]?.title ?? "",
        article_type: current[issue.record_id as string]?.article_type ?? "",
        [field]: value,
      },
    }));
  }

  async function savePublicationCorrections() {
    if (!task) return;
    const payload = Object.fromEntries(editableRecords.map((issue) => [
      issue.record_id as string,
      publicationCorrections[issue.record_id as string] ?? { title: "", article_type: "" },
    ]));
    if (Object.values(payload).some((item) => !item.title.trim() || !item.article_type)) {
      setError("请为每条待补充记录同时填写作品标题和作品类型。");
      return;
    }
    setSaving(true);
    setError("");
    setCorrectionMessage("");
    try {
      await api.submitPublicationCorrections(task.task_id, payload);
      const updated = await api.getTask(task.task_id);
      setTasks((items) => items.map((item) => item.task_id === updated.task_id ? updated : item));
      setCorrectionMessage("补充内容已保存，系统正在重新校验并生成结果。");
    } catch (err) {
      setError(errorMessage(err, "保存补充内容失败"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <Hero title="约稿资料" subtitle="选择任意一次处理记录，查看并筛选该次约稿明细" />
      {error ? <div className="alert error">{error}</div> : null}
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
      ) : error ? null : (
        <div className="alert info">尚无任务。请先在「数据处理」上传链接表。</div>
      )}

      {task?.status === "failed" ? (
        <div className="alert error">该次处理未完成，请根据下方提示修正数据后重新处理。</div>
      ) : task && completed && details.length ? (
        <div className="alert success">正在展示该次处理的可入账约稿明细。</div>
      ) : task && completed ? (
        <div className="alert info">该次任务已完成，但没有可入账的约稿记录。</div>
      ) : task ? (
        <div className="alert info">
          该次任务「{TASK_STATUS_LABEL[task.status]}」，完成后才会生成约稿明细。
        </div>
      ) : null}

      <IssueList issues={issues} title="该次处理问题" />

      {task && editableRecords.length > 0 && task.status !== "running" ? (
        <div className="panel">
          <h2>在线补充作品信息</h2>
          <p style={{ color: "var(--muted)" }}>
            对于网页未能自动读取的记录，请填写作品标题并确认作品类型。保存后系统会重新校验和计算费用。
          </p>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>涉及数据</th>
                  <th>作品标题（必填）</th>
                  <th>作品类型（必填）</th>
                </tr>
              </thead>
              <tbody>
                {editableRecords.map((issue) => (
                  <tr key={issue.record_id}>
                    <td>
                      {issue.row_number ? `Excel 第 ${issue.row_number} 行` : "本次记录"}
                      {issue.media_name ? ` · ${issue.media_name}` : ""}
                    </td>
                    <td>
                      <input
                        type="text"
                        value={publicationCorrections[issue.record_id as string]?.title ?? ""}
                        onChange={(event) => updatePublicationCorrection(issue, "title", event.target.value)}
                        placeholder="请输入作品标题"
                      />
                    </td>
                    <td>
                      <select
                        value={publicationCorrections[issue.record_id as string]?.article_type ?? ""}
                        onChange={(event) => updatePublicationCorrection(issue, "article_type", event.target.value)}
                      >
                        <option value="">请选择</option>
                        <option value="图文">图文</option>
                        <option value="视频">视频</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button className="btn primary" disabled={saving} onClick={() => void savePublicationCorrections()}>
            {saving ? "保存中…" : "保存并重新校验"}
          </button>
        </div>
      ) : null}
      {correctionMessage ? <div className="alert info">{correctionMessage}</div> : null}

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
