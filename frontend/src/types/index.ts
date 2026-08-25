export type Role = "admin" | "operator" | "finance" | "viewer";

export type UserStatus = "pending" | "active" | "disabled";

export type TaskStatus =
  | "needs_correction"
  | "ready"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type ExceptionStatus = "待确认" | "待校对" | "已解决";

export type QuoteStatus = "完成" | "待确认";

export interface User {
  id: string;
  email: string;
  name: string;
  role: Role;
  status: UserStatus;
  created_at: string;
  last_login_at: string | null;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface AuthSession {
  user: User;
  tokens: AuthTokens;
}

export interface ApiErrorBody {
  detail: string;
  code?: string;
  field_errors?: Record<string, string>;
}

export interface MediaRecord {
  record_id: string;
  row_number: number;
  topic: string;
  media_name: string;
  link_count: number;
  link_preview: string;
  match_status: "matched" | "unmatched";
  suggested_name: string;
}

export interface TaskIssue {
  record_id?: string;
  code: string;
  message: string;
  severity: "warning" | "error" | "critical";
}

export interface ValidateTaskResponse {
  task_id: string;
  status: TaskStatus;
  records: MediaRecord[];
  issues: TaskIssue[];
  allowed_media_names: string[];
}

export interface TaskFileKey {
  key: "quote_detail" | "payment";
  filename: string;
  ready: boolean;
}

export interface QuoteDetail {
  media_name: string;
  platform: string;
  content_type: string;
  media_level: string;
  followers: string;
  quote_count: number;
  unit_price: number;
  amount: number;
  status: QuoteStatus;
  title: string;
  publish_url: string;
  publish_date: string;
}

export interface QuoteSummary {
  media_count: number;
  quote_count: number;
  total_fee: number;
  text_fee: number;
  video_fee: number;
  details: QuoteDetail[];
}

export interface TaskProgress {
  completed_nodes: string[];
  total_nodes: number;
  current_node: string | null;
}

export interface Task {
  task_id: string;
  status: TaskStatus;
  filename: string;
  created_at: string;
  updated_at: string;
  created_by: string;
  error: string | null;
  progress: TaskProgress;
  quote_summary: QuoteSummary | null;
  files: TaskFileKey[];
  issues: TaskIssue[];
}

export interface MonthlyBatch {
  task_id: string;
  processed_at: string;
  quote_count: number;
  total_fee: number;
  text_fee: number;
  video_fee: number;
}

export interface MonthlyAnalytics {
  month: string;
  batch_count: number;
  quote_count: number;
  total_fee: number;
  average_batch_fee: number;
  batches: MonthlyBatch[];
  top_media: { media: string; total_fee: number }[];
}

export interface DashboardOverview {
  latest_task: Task | null;
  task_status_label: string;
  media_count: number;
  quote_count: number;
  total_fee: number;
  type_distribution: { content_type: string; quote_count: number }[];
  pending_exceptions: number;
  config_ready: boolean;
}

export interface ConfigFileStatus {
  kind: ConfigKind;
  label: string;
  configured: boolean;
  filename: string | null;
  updated_at: string | null;
  updated_by: string | null;
}

export type ConfigKind =
  | "quote_template"
  | "media_library"
  | "accounts"
  | "fee_rules"
  | "payment_template";

export interface ConfigStatus {
  files: ConfigFileStatus[];
  all_ready: boolean;
}

export interface FeeLine {
  media_name: string;
  platform: string;
  content_type: string;
  work_count: number;
  fee_rule: string;
  unit_price: number;
  expected_fee: number;
}

export interface FeeCompareRow {
  media_name: string;
  detail_fee: number;
  summary_fee: number;
  status: "一致" | "不一致";
}

export interface ExceptionItem {
  exception_id: string;
  task_id: string;
  target: string;
  issue: string;
  suggestion: string;
  status: ExceptionStatus;
  correction: string;
  calculation: FeeLine[];
  compare: FeeCompareRow[];
}

export interface UserListItem extends User {
  note?: string;
}

export const ROLE_LABEL: Record<Role, string> = {
  admin: "管理员",
  operator: "业务人员",
  finance: "财务",
  viewer: "只读访客",
};

export const STATUS_LABEL: Record<UserStatus, string> = {
  pending: "待审核",
  active: "已启用",
  disabled: "已停用",
};

export const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  needs_correction: "待修正",
  ready: "待执行",
  running: "处理中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

export const NODE_LABELS = [
  "链接解析",
  "资料整理",
  "媒体匹配",
  "账户补全",
  "费用计算",
  "付款生成",
] as const;

export const PAGE_ROLES: Record<string, Role[]> = {
  "/": ["admin", "operator", "finance", "viewer"],
  "/processing": ["admin", "operator"],
  "/quotes": ["admin", "operator", "finance", "viewer"],
  "/analytics": ["admin", "operator", "finance", "viewer"],
  "/exceptions": ["admin", "operator"],
  "/exports": ["admin", "operator", "finance"],
  "/config": ["admin"],
  "/users": ["admin"],
  "/account": ["admin", "operator", "finance", "viewer"],
};
