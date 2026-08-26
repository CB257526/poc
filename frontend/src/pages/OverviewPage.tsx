import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { ApiError, yuan } from "../api/client";
import { Hero, Metric, StatusPill } from "../components/ui";
import { NODE_LABELS, TASK_STATUS_LABEL, type DashboardOverview } from "../types";

export function OverviewPage() {
  const [data, setData] = useState<DashboardOverview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.overview().then(setData).catch((err: unknown) => {
      setError(err instanceof ApiError ? err.message : "加载失败");
    });
  }, []);

  if (error) return <div className="alert error">{error}</div>;
  if (!data) return <p>加载中…</p>;

  const completed = data.latest_task?.status === "completed";
  const hasQuotes = Boolean(data.latest_task?.quote_summary?.details?.length);

  return (
    <>
      <Hero title="约稿平台" subtitle="自动完成约稿资料整理、媒体信息匹配、费用计算及付款生成" />
      <div className="metrics">
        <Metric
          label="任务状态"
          value={data.task_status_label}
          hint={data.latest_task ? TASK_STATUS_LABEL[data.latest_task.status] : "尚无任务"}
        />
        <Metric label="媒体数量" value={String(data.media_count)} hint={completed ? "已完成匹配" : "完成任务后统计"} />
        <Metric label="约稿数量" value={String(data.quote_count)} hint="仅含校验通过数据" />
        <Metric label="费用总额" value={yuan(data.total_fee)} hint="仅含校验通过数据" />
      </div>
      <div className="panel">
        <h2>业务处理流程</h2>
        <div className="flow">
          {NODE_LABELS.map((step, index) => (
            <div className="flow-step" key={step}>
              <span className="flow-num">{index + 1}</span>
              <br />
              {step}
            </div>
          ))}
        </div>
      </div>
      <div className="grid-2">
        <div className="panel">
          <h3>本次约稿类型分布</h3>
          {hasQuotes ? (
            <div style={{ height: 230 }}>
              <ResponsiveContainer>
                <BarChart data={data.type_distribution} barCategoryGap="28%">
                  <CartesianGrid vertical={false} stroke="#e8ecf3" />
                  <XAxis dataKey="content_type" tickLine={false} axisLine={false} />
                  <YAxis tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip formatter={(value) => [String(value), "约稿数量"]} />
                  <Bar dataKey="quote_count" fill="#165dff" radius={[4, 4, 0, 0]} maxBarSize={72} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="empty">暂无已完成任务的约稿明细。请先在「数据处理」上传链接表。</p>
          )}
        </div>
        <div className="panel">
          <b>本次处理结果</b>
          <p>
            {data.pending_exceptions > 0 ? (
              <StatusPill kind="warn">{data.pending_exceptions} 项待确认</StatusPill>
            ) : (
              <StatusPill kind="done">无待处理异常</StatusPill>
            )}
          </p>
          <p>
            {completed
              ? "当前指标来自最近一次已完成任务，异常记录未计入费用与月度统计。"
              : data.latest_task
                ? `最近任务状态为「${TASK_STATUS_LABEL[data.latest_task.status]}」，完成后才会计入费用。`
                : "尚未处理过任务。"}
          </p>
          {!data.config_ready ? <p className="alert warn">基础配置未齐，管理员需先上传媒体库、账户和费用表。</p> : null}
        </div>
      </div>
    </>
  );
}
