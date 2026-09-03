import type { ReactNode } from "react";
import type { TaskIssue } from "../types";
import { ISSUE_SEVERITY_LABEL } from "../types";

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

type BusinessIssue = {
  title: string;
  description: string;
  suggestion: string;
};

const BUSINESS_ISSUES: Record<string, BusinessIssue> = {
  INPUT_FILE_NOT_FOUND: {
    title: "未找到链接表",
    description: "系统没有找到本次需要处理的链接表。",
    suggestion: "请重新上传链接表后再开始处理。",
  },
  REFERENCE_TABLE_NOT_FOUND: {
    title: "基础资料未配置",
    description: "本次处理需要的基础资料尚未配置完整。",
    suggestion: "请联系管理员补充对应的基础资料。",
  },
  EMPTY_INPUT_FILE: {
    title: "链接表没有有效数据",
    description: "上传的链接表中没有读取到可处理的媒体和链接。",
    suggestion: "请检查表格内容后重新上传。",
  },
  READ_INPUT_FILE_FAILED: {
    title: "链接表读取失败",
    description: "系统暂时无法读取上传的链接表。",
    suggestion: "请确认文件为正确的 Excel 模板且未损坏，然后重新上传。",
  },
  MEDIA_TABLE_LOAD_FAILED: {
    title: "媒体库读取失败",
    description: "系统暂时无法读取已配置的媒体库。",
    suggestion: "请联系管理员检查媒体库文件。",
  },
  TABLE_LOAD_FAILED: {
    title: "基础资料读取失败",
    description: "系统暂时无法读取本次处理需要的基础资料。",
    suggestion: "请联系管理员检查对应的配置文件。",
  },
  MISSING_REQUIRED_FIELD: {
    title: "链接表信息不完整",
    description: "该行缺少本次处理所需的必填信息。",
    suggestion: "请补充表格中的必填内容后重新处理。",
  },
  MEDIA_NOT_IN_LIBRARY: {
    title: "媒体名称无法匹配",
    description: "链接表中的媒体名称与媒体库不一致。",
    suggestion: "请在修正面板填写正确的媒体名称后继续处理。",
  },
  INVALID_URL: {
    title: "发布链接格式不正确",
    description: "该链接不是系统可识别的有效网页地址。",
    suggestion: "请检查并更正发布链接。",
  },
  NO_URL_FOUND: {
    title: "缺少发布链接",
    description: "该条约稿没有填写发布链接。",
    suggestion: "请补充发布链接后重新处理。",
  },
  UNKNOWN_PLATFORM: {
    title: "发布平台无法识别",
    description: "系统无法根据当前链接判断发布平台。",
    suggestion: "请检查链接是否完整、是否属于支持的平台。",
  },
  DUPLICATE_LINKS_MERGED: {
    title: "重复链接已合并",
    description: "系统发现同一主题下存在重复链接，并已按一条约稿合并处理。",
    suggestion: "无需处理；如内容并非重复，请检查原始链接表。",
  },
  DUPLICATE_URL: {
    title: "发现重复发布链接",
    description: "该发布链接在本次数据中重复出现。",
    suggestion: "请确认是否为重复填报。",
  },
  SCRAPE_FAILED: {
    title: "网页信息获取失败",
    description: "系统暂时未能打开该发布链接，因此没有读取到作品信息。",
    suggestion: "请确认链接可以正常访问后重试；仍失败时可人工核验。",
  },
  SCRAPING_UNAVAILABLE: {
    title: "网页读取服务暂不可用",
    description: "系统当前无法自动读取发布网页的信息。",
    suggestion: "请稍后重试或联系技术人员检查网页读取服务。",
  },
  MISSING_TITLE: {
    title: "作品标题未识别",
    description: "系统已访问发布链接，但没有识别到作品标题。",
    suggestion: "请人工确认该链接对应的作品。",
  },
  MISSING_ARTICLE_TYPE: {
    title: "作品类型待确认",
    description: "系统暂未识别该作品属于图文还是视频。",
    suggestion: "请人工确认作品类型，并核对所采用的费用标准。",
  },
  MISSING_MEDIA_NAME: {
    title: "媒体名称缺失",
    description: "该条数据没有可用于匹配的媒体名称。",
    suggestion: "请补充媒体名称后重新处理。",
  },
  DUPLICATE_MEDIA_NAME: {
    title: "媒体库存在重名",
    description: "媒体库中存在多个相同名称，系统无法确定应使用哪条资料。",
    suggestion: "请联系管理员整理媒体库中的重复记录。",
  },
  MEDIA_NOT_FOUND: {
    title: "未找到媒体资料",
    description: "系统未在媒体库中找到该媒体的资料。",
    suggestion: "请检查媒体名称，或联系管理员补充媒体库。",
  },
  MISSING_MEDIA_LEVEL: {
    title: "媒体等级缺失",
    description: "媒体库中没有该媒体的等级信息，暂时无法匹配费用规则。",
    suggestion: "请联系管理员补充媒体等级。",
  },
  MISSING_FAN_COUNT: {
    title: "粉丝量信息缺失",
    description: "媒体库中没有该媒体的粉丝量信息。",
    suggestion: "请联系管理员补充粉丝量。",
  },
  DUPLICATE_ACCOUNT_MEDIA: {
    title: "账户信息存在重名",
    description: "账户信息表中存在多个同名媒体，系统无法自动选择账户。",
    suggestion: "请联系管理员整理账户信息表中的重复记录。",
  },
  MISSING_ACCOUNT_FIELDS: {
    title: "账户信息不完整",
    description: "该媒体的收款账户缺少付款所需的信息。",
    suggestion: "请补充账户信息后再生成付款文件。",
  },
  ACCOUNT_NOT_FOUND: {
    title: "未找到收款账户",
    description: "系统未在账户信息表中找到该媒体对应的收款账户。",
    suggestion: "请检查媒体名称，或补充账户信息。",
  },
  FEE_RULE_NOT_FOUND: {
    title: "未找到费用标准",
    description: "现有费用规则无法匹配该媒体的等级和作品类型。",
    suggestion: "请联系管理员补充费用规则，并人工核对本条费用。",
  },
  NO_QUOTE_DETAILS: {
    title: "没有可生成的约稿明细",
    description: "本次处理没有形成有效的约稿费用明细。",
    suggestion: "请先处理前面提示的数据问题。",
  },
  NO_ELIGIBLE_QUOTE_DETAILS: {
    title: "没有可入账的约稿明细",
    description: "本次数据中没有符合付款条件的约稿记录。",
    suggestion: "请检查媒体、账户和费用信息是否完整。",
  },
  GENERATION_FAILED: {
    title: "付款文件生成失败",
    description: "系统未能完成付款文件的生成。",
    suggestion: "请稍后重试；仍失败时联系技术人员处理。",
  },
  PROCESSING_ERROR: {
    title: "该条数据处理失败",
    description: "系统未能完成该条数据的自动处理。",
    suggestion: "请检查对应数据；仍无法处理时联系技术人员。",
  },
  NODE_EXECUTION_FAILED: {
    title: "处理步骤执行失败",
    description: "系统未能完成本次任务中的一个处理步骤。",
    suggestion: "请重新处理；仍失败时联系技术人员。",
  },
};

function businessIssue(issue: TaskIssue): BusinessIssue {
  const mapped = BUSINESS_ISSUES[issue.code];
  if (mapped) {
    if (issue.code === "SCRAPE_FAILED" && /timeout|超时/i.test(issue.message)) {
      return {
        title: "网页访问超时",
        description: "系统在规定时间内未能打开该发布链接，因此没有读取到作品信息。",
        suggestion: mapped.suggestion,
      };
    }
    return mapped;
  }
  return {
    title: issue.severity === "warning" ? "数据需要确认" : "数据处理未完成",
    description: issue.severity === "warning"
      ? "系统发现该条数据需要人工确认。"
      : "系统未能完成该条数据的自动处理。",
    suggestion: "请检查对应数据；如无法判断，请联系技术人员查看后台日志。",
  };
}

function issueRecordLabel(issue: TaskIssue) {
  if (issue.row_number) {
    return `Excel 第 ${issue.row_number} 行${issue.media_name ? ` · ${issue.media_name}` : ""}`;
  }
  if (issue.media_name) return issue.media_name;
  return "本次任务";
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
              <th>问题</th>
              <th>涉及数据</th>
              <th>原因说明</th>
              <th>处理建议</th>
            </tr>
          </thead>
          <tbody>
            {issues.map((issue, index) => {
              const display = businessIssue(issue);
              return (
                <tr key={`${issue.code}-${issue.record_id ?? ""}-${index}`}>
                  <td>
                    <StatusPill kind={severityKind(issue.severity)}>
                      {ISSUE_SEVERITY_LABEL[issue.severity] ?? issue.severity}
                    </StatusPill>
                  </td>
                  <td>{display.title}</td>
                  <td>{issueRecordLabel(issue)}</td>
                  <td>{display.description}</td>
                  <td>{display.suggestion}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
