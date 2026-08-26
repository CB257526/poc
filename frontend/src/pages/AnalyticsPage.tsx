import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api";
import { ApiError, formatDate, yuan } from "../api/client";
import { Hero, Metric } from "../components/ui";
import type { MonthlyAnalytics, QuoteDetail } from "../types";

function isTextType(type: string) {
  return ["图文", "文章", "图文类"].includes(type);
}

function isVideoType(type: string) {
  return ["视频", "视频类"].includes(type);
}

export function AnalyticsPage() {
  const [analytics, setAnalytics] = useState<MonthlyAnalytics | null>(null);
  const [details, setDetails] = useState<QuoteDetail[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.monthly(), api.quotes()])
      .then(([month, quotes]) => {
        setAnalytics(month);
        setDetails(quotes.details);
      })
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "加载失败"));
  }, []);

  if (error) return <div className="alert error">{error}</div>;
  if (!analytics) return <p>加载中…</p>;

  const currentTotal = details.reduce((sum, row) => sum + row.amount, 0);
  const textTotal = details.filter((row) => isTextType(row.content_type)).reduce((sum, row) => sum + row.amount, 0);
  const videoTotal = details.filter((row) => isVideoType(row.content_type)).reduce((sum, row) => sum + row.amount, 0);
  const top = analytics.top_media.map((item) => ({ name: item.media, amount: item.total_fee }));
  const lineData = analytics.batches.map((batch, index) => ({
    date: formatDate(batch.processed_at),
    batch: `批次 ${String(index + 1).padStart(2, "0")}`,
    quote_count: batch.quote_count,
    total_fee: batch.total_fee,
    text_fee: batch.text_fee,
    video_fee: batch.video_fee,
  }));

  return (
    <>
      <Hero title="费用分析" subtitle="查看本次任务费用，以及系统历史记录形成的当月累计汇总" />
      <div className="alert success">
        统计口径：仅累计已通过媒体、账户及费用校验的约稿记录；待修改、待确认或处理失败的数据不会计入当月汇总。
      </div>
      <div className="panel">
        <h2>本次费用概览</h2>
        {details.length === 0 ? <p className="empty">最近一次任务尚无可入账明细。</p> : null}
        <div className="metrics">
          <Metric label="本次总费用" value={yuan(currentTotal)} />
          <Metric label="本次图文费用" value={yuan(textTotal)} hint={currentTotal ? `${((textTotal / currentTotal) * 100).toFixed(1)}%` : "0%"} />
          <Metric label="本次视频费用" value={yuan(videoTotal)} hint={currentTotal ? `${((videoTotal / currentTotal) * 100).toFixed(1)}%` : "0%"} />
        </div>
      </div>
      <div className="panel">
        <h2>当月 TOP 媒体费用</h2>
        <p style={{ color: "var(--muted)" }}>汇总系统当月保存的约稿记录，并按媒体费用从高到低展示。</p>
        {top.length ? (
          <div style={{ height: 330 }}>
            <ResponsiveContainer>
              <BarChart data={top} barCategoryGap="22%">
                <CartesianGrid vertical={false} stroke="#e8ecf3" />
                <XAxis dataKey="name" tickLine={false} axisLine={false} interval={0} />
                <YAxis tickLine={false} axisLine={false} tickFormatter={(v: number) => `${Math.round(v / 1000)}k`} />
                <Tooltip formatter={(value) => [yuan(Number(value)), "费用"]} />
                <Bar dataKey="amount" fill="#165dff" radius={[4, 4, 0, 0]} maxBarSize={64} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="empty">本月暂无已入账的媒体费用。</p>
        )}
      </div>
      <div className="panel">
        <h2>当月费用汇总</h2>
        <p style={{ color: "var(--muted)" }}>当前展示 {analytics.month} 月处理记录。</p>
        <div className="metrics">
          <Metric label="当月累计费用" value={yuan(analytics.total_fee)} />
          <Metric label="当月处理批次" value={`${analytics.batch_count} 次`} />
          <Metric label="当月约稿数量" value={`${analytics.quote_count} 条`} />
          <Metric label="平均每批费用" value={yuan(analytics.average_batch_fee)} />
        </div>
        {lineData.length ? (
          <>
            <div style={{ height: 300, marginTop: 8 }}>
              <ResponsiveContainer>
                <LineChart data={lineData}>
                  <CartesianGrid vertical={false} stroke="#e8ecf3" />
                  <XAxis dataKey="date" tickLine={false} axisLine={false} />
                  <YAxis tickLine={false} axisLine={false} tickFormatter={(v: number) => `${Math.round(v / 1000)}k`} />
                  <Tooltip
                    formatter={(value, name) => {
                      if (name === "total_fee") return [yuan(Number(value)), "费用总额"];
                      if (name === "quote_count") return [String(value), "约稿数量"];
                      return [String(value), String(name)];
                    }}
                  />
                  <Line type="monotone" dataKey="total_fee" stroke="#165dff" strokeWidth={3} dot={{ r: 5, fill: "#165dff" }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="table-wrap" style={{ marginTop: 16 }}>
              <table className="data">
                <thead>
                  <tr>
                    <th>上传日期</th>
                    <th>处理批次</th>
                    <th>约稿数量</th>
                    <th>图文费用</th>
                    <th>视频费用</th>
                    <th>费用总额</th>
                  </tr>
                </thead>
                <tbody>
                  {lineData.map((row) => (
                    <tr key={row.batch}>
                      <td>{row.date}</td>
                      <td>{row.batch}</td>
                      <td>{row.quote_count}</td>
                      <td>{yuan(row.text_fee)}</td>
                      <td>{yuan(row.video_fee)}</td>
                      <td>{yuan(row.total_fee)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="empty">本月尚无已完成的处理批次。</p>
        )}
      </div>
    </>
  );
}
