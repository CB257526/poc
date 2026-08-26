import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { ApiError, yuan } from "../api/client";
import { Hero } from "../components/ui";
import type { QuoteDetail, Task } from "../types";
import { TASK_STATUS_LABEL } from "../types";

export function QuotesPage() {
  const [task, setTask] = useState<Task | null>(null);
  const [details, setDetails] = useState<QuoteDetail[]>([]);
  const [error, setError] = useState("");
  const [level, setLevel] = useState("全部");
  const [platform, setPlatform] = useState("全部");
  const [state, setState] = useState("全部");

  useEffect(() => {
    api.quotes()
      .then((result) => {
        setTask(result.task);
        setDetails(result.details);
      })
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "加载失败"));
  }, []);

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

  if (error) return <div className="alert error">{error}</div>;

  const completed = task?.status === "completed";

  return (
    <>
      <Hero title="约稿资料" subtitle="查看、筛选本次处理后的约稿明细" />
      {completed && details.length
        ? <div className="alert success">当前展示最近一次任务返回的约稿明细。</div>
        : completed
          ? <div className="alert info">最近一次任务已完成，但没有可入账的约稿记录。</div>
          : <div className="alert info">{task ? `最近任务「${TASK_STATUS_LABEL[task.status]}」，完成后才会生成约稿明细。` : "尚无任务。请先在「数据处理」上传链接表。"}</div>}
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
                    <th>单价</th>
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
                      <td>{yuan(row.unit_price)}</td>
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
