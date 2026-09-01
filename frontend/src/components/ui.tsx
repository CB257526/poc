import type { ReactNode } from "react";
import type { TaskIssue } from "../types";
import { ISSUE_SEVERITY_LABEL, NODE_ID_LABEL } from "../types";

export function Hero({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="hero">
      <h1>{title}</h1>
      <p>{subtitle}</p>
    </div>
  );
}

export function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="metric">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {hint ? <div className="hint">{hint}</div> : null}
    </div>
  );
}

export function StatusPill({ kind, children }: { kind: "done" | "warn" | "bad" | "idle"; children: ReactNode }) {
  return <span className={`status ${kind}`}>{children}</span>;
}

function severityKind(severity: TaskIssue["severity"]): "warn" | "bad" {
  return severity === "warning" ? "warn" : "bad";
}

export function IssueList({ issues, title = "处理问题" }: { issues: TaskIssue[]; title?: string }) {
  if (!issues.length) return null;
  return (
    <div className="panel">
      <h2>{title}</h2>
      <p style={{ color: "var(--muted)" }}>共 {issues.length} 条。严重/错误会影响入账，警告一般仍可完成任务。</p>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>级别</th>
              <th>节点</th>
              <th>代码</th>
              <th>说明</th>
              <th>记录</th>
            </tr>
          </thead>
          <tbody>
            {issues.map((issue, index) => (
              <tr key={`${issue.code}-${issue.record_id ?? ""}-${index}`}>
                <td>
                  <StatusPill kind={severityKind(issue.severity)}>
                    {ISSUE_SEVERITY_LABEL[issue.severity] ?? issue.severity}
                  </StatusPill>
                </td>
                <td>{issue.node_id ? (NODE_ID_LABEL[issue.node_id] ?? issue.node_id) : "—"}</td>
                <td>{issue.code}</td>
                <td>{issue.message}</td>
                <td>
                  {issue.row_number
                    ? `第 ${issue.row_number} 行${issue.media_name ? ` · ${issue.media_name}` : ""}`
                    : issue.record_id || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
