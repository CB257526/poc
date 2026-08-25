import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { ApiError } from "../api/client";
import { Hero, Metric, StatusPill } from "../components/ui";
import { yuan } from "../api/client";
import { NODE_LABELS, type DashboardOverview } from "../types";

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

  const live = Boolean(data.latest_task?.quote_summary);

  return (
    <>
      <Hero title="约稿平台" subtitle="自动完成约稿资料整理、媒体信息匹配、费用计算及付款生成" />
      <div className="metrics">
        <Metric label="任务状态" value={data.task_status_label} hint={live ? "本次文件 1 / 1" : "演示模式"} />
        <Metric label="媒体数量" value={String(data.media_count)} hint={live ? "已完成匹配" : "演示数据"} />
        <Metric label="约稿数量" value={String(data.quote_count)} hint={live ? "真实任务结果" : "图文 + 视频"} />
        <Metric label="费用总额" value={yuan(data.total_fee)} hint="仅含校验通过数据" />
      </div>
      <div className="panel">
        <h2>业务处理流程</h2>
        <div className="flow">
          {NODE_LABELS.map((step, index) => (
            <div className="flow-step" key={step}>
              <span className="flow-num">✓ {index + 1}</span>
              <br />
              {step}
            </div>
          ))}
        </div>
      </div>
      <div className="grid-2">
        <div className="panel">
          <h3>本次约稿类型分布</h3>
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
        </div>
        <div className="panel">
          <b>本次处理结果</b>
          <p>
            {data.pending_exceptions > 0 ? (
              <StatusPill kind="warn">{data.pending_exceptions} 项待确认</StatusPill>
            ) : (
              <StatusPill kind="done">全部通过</StatusPill>
            )}
          </p>
          <p>
            {live
              ? "当前指标来自最近一次任务，异常记录未计入费用与月度统计。"
              : "「约稿」与「约稿费用合计」存在金额不一致，请到异常提醒核对。"}
          </p>
        </div>
      </div>
    </>
  );
}
