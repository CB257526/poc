import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { ApiError, yuan } from "../api/client";
import { Hero, Metric, StatusPill } from "../components/ui";
import type { ExceptionItem } from "../types";

export function ExceptionsPage() {
  const [items, setItems] = useState<ExceptionItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [summaryFees, setSummaryFees] = useState<Record<string, number>>({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function reload() {
    const list = await api.listExceptions();
    setItems(list);
  }

  useEffect(() => {
    reload().catch((err: unknown) => setError(err instanceof ApiError ? err.message : "加载失败"));
  }, []);

  const selected = items.find((item) => item.exception_id === selectedId) ?? null;
  const unresolved = items.filter((item) => item.status !== "已解决");

  useEffect(() => {
    const item = items.find((row) => row.exception_id === selectedId);
    if (!item) return;
    setSummaryFees(Object.fromEntries(item.compare.map((row) => [row.media_name, row.summary_fee])));
  }, [selectedId, items]);

  const merged = useMemo(() => {
    if (!selected) return [];
    return selected.compare.map((row) => {
      const summary = summaryFees[row.media_name] ?? row.summary_fee;
      return {
        ...row,
        current_summary: summary,
        delta: summary - row.detail_fee,
        matched: summary === row.detail_fee,
      };
    });
  }, [selected, summaryFees]);

  const amountsMatch = merged.length > 0 && merged.every((row) => row.matched);
  const detailTotal = selected?.compare.reduce((sum, row) => sum + row.detail_fee, 0) ?? 0;
  const summaryTotal = merged.reduce((sum, row) => sum + row.current_summary, 0);
  const mismatch = merged.find((row) => !row.matched);

  async function save() {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await api.saveException(selected.exception_id, summaryFees);
      await reload();
      setSelectedId(null);
      setMessage("修改已保存，请点击「重新校对」执行规则验证。");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function reaudit() {
    setBusy(true);
    setError("");
    try {
      const result = await api.reauditExceptions();
      await reload();
      setMessage(`重新校对完成：${result.resolved} 项已通过，${result.remaining} 项仍需处理。`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "校对失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Hero title="费用一致性校验" subtitle="核对「约稿」与「约稿费用合计」两个子表的费用" />
      <div className="metrics">
        <Metric label="待处理事项" value={String(unresolved.length)} />
        <Metric label="待确认" value={String(items.filter((i) => i.status === "待确认").length)} />
        <Metric label="待校对" value={String(items.filter((i) => i.status === "待校对").length)} />
      </div>
      {error ? <div className="alert error">{error}</div> : null}
      {message ? <div className={unresolved.length === 0 ? "alert success" : "alert info"}>{message}</div> : null}

      <div className="panel">
        <h2>待处理事项</h2>
        <p style={{ color: "var(--muted)" }}>点击右侧状态按钮打开对应核验表；红色标记表示需要人工修改或确认的数据。</p>
        {items.length === 0 ? <p className="empty">暂无费用一致性异常。</p> : null}
        {items.map((item) => (
          <div className="file-row" key={item.exception_id}>
            <div>
              <b>{item.target}</b>
              <div>{item.issue}</div>
              <div style={{ color: "var(--muted)", fontSize: 13 }}>{item.suggestion}</div>
            </div>
            {item.status === "已解决" ? (
              <StatusPill kind="done">已解决</StatusPill>
            ) : (
              <button className="btn" onClick={() => setSelectedId(item.exception_id)}>{item.status}</button>
            )}
          </div>
        ))}
      </div>

      {selected ? (
        <div className="panel">
          <h2>处理异常 · {selected.target}</h2>
          <div className="alert error">需要处理：{selected.issue}</div>
          {selected.calculation.length ? (
            <>
              <h3>① 异常定位与计算依据</h3>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>媒体名称</th>
                      <th>发布平台</th>
                      <th>内容类型</th>
                      <th>作品数量</th>
                      <th>匹配费用规则</th>
                      <th>核定单价</th>
                      <th>应计费用</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selected.calculation.map((row, index) => (
                      <tr key={`${row.media_name}-${index}`}>
                        <td>{row.media_name}</td>
                        <td>{row.platform}</td>
                        <td>{row.content_type}</td>
                        <td>{row.work_count}</td>
                        <td>{row.fee_rule}</td>
                        <td>{yuan(row.unit_price)}</td>
                        <td>{yuan(row.expected_fee)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="alert info">
                系统计算依据：{selected.calculation[0].media_name} 共 {selected.calculation.reduce((s, r) => s + r.work_count, 0)} 条
                × 核定单价 {yuan(selected.calculation[0].unit_price)} = 应计费用 {yuan(selected.calculation.reduce((s, r) => s + r.expected_fee, 0))}。
              </div>
            </>
          ) : null}
          <h3>② 两个子表逐媒体对照</h3>
          <div className="grid-2">
            <div>
              <b>子表：约稿</b>
              <table className="data">
                <thead><tr><th>媒体名称</th><th>约稿子表费用</th></tr></thead>
                <tbody>
                  {selected.compare.map((row) => (
                    <tr key={row.media_name}><td>{row.media_name}</td><td>{yuan(row.detail_fee)}</td></tr>
                  ))}
                </tbody>
              </table>
              <Metric label="约稿总费用" value={yuan(detailTotal)} />
            </div>
            <div>
              <b>子表：约稿费用合计</b>
              <table className="data">
                <thead><tr><th>媒体名称</th><th>约稿费用合计</th><th>核验状态</th></tr></thead>
                <tbody>
                  {merged.map((row) => (
                    <tr key={row.media_name} className={row.matched ? undefined : "mismatch"}>
                      <td>{row.media_name}</td>
                      <td>
                        <input
                          type="number"
                          min={0}
                          value={row.current_summary}
                          onChange={(e) => setSummaryFees((prev) => ({ ...prev, [row.media_name]: Number(e.target.value) }))}
                        />
                      </td>
                      <td>{row.matched ? "一致" : "🔴 不一致"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Metric label="费用合计总额" value={yuan(summaryTotal)} />
            </div>
          </div>
          {mismatch
            ? <div className="alert warn">当前差异：{mismatch.media_name} 在「约稿费用合计」中差额 {yuan(Math.abs(mismatch.delta))}；建议依据上方明细将金额确认至 {yuan(mismatch.detail_fee)}。</div>
            : <div className="alert success">两个子表的逐媒体金额和总费用现已一致，可以保存核验结果。</div>}
          <div style={{ display: "flex", gap: 12, marginTop: 12 }}>
            <button className="btn primary" disabled={busy || !amountsMatch} onClick={() => void save()}>保存核验结果</button>
            <button className="btn ghost" onClick={() => setSelectedId(null)}>返回异常列表</button>
          </div>
        </div>
      ) : null}

      <button className="btn primary" disabled={busy} onClick={() => void reaudit()}>重新校对</button>
      <p className="alert warn">异常中心展示两个子表的费用一致性校验，不对后台账户信息重复核验。</p>
    </>
  );
}
