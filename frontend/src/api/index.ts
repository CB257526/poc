import { ApiError, isMockEnabled, request, requestBlob, setTokens, clearTokens } from "./client";
import {
  completedTask,
  configStatus,
  dashboardOverview,
  DEMO_PASSWORD,
  exceptions as seedExceptions,
  mediaLibrary,
  monthlyAnalytics,
  quoteDetails,
  seedUsers,
  validateNeedsCorrection,
} from "../mock/data";
import type {
  AuthSession,
  ConfigKind,
  ConfigStatus,
  DashboardOverview,
  ExceptionItem,
  FeeCompareRow,
  MonthlyAnalytics,
  Role,
  Task,
  User,
  UserStatus,
  ValidateTaskResponse,
} from "../types";

function wait(ms = 280) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

const USERS_KEY = "quote.mock.users";
const SESSION_KEY = "quote.mock.session";
const TASK_KEY = "quote.mock.task";
const EXCEPTIONS_KEY = "quote.mock.exceptions";
const CONFIG_KEY = "quote.mock.config";

function loadUsers(): User[] {
  const raw = localStorage.getItem(USERS_KEY);
  if (raw) return JSON.parse(raw) as User[];
  localStorage.setItem(USERS_KEY, JSON.stringify(seedUsers));
  return clone(seedUsers);
}

function saveUsers(users: User[]) {
  localStorage.setItem(USERS_KEY, JSON.stringify(users));
}

function loadExceptions(): ExceptionItem[] {
  const raw = localStorage.getItem(EXCEPTIONS_KEY);
  if (raw) return JSON.parse(raw) as ExceptionItem[];
  localStorage.setItem(EXCEPTIONS_KEY, JSON.stringify(seedExceptions));
  return clone(seedExceptions);
}

function saveExceptions(items: ExceptionItem[]) {
  localStorage.setItem(EXCEPTIONS_KEY, JSON.stringify(items));
}

function loadConfig(): ConfigStatus {
  const raw = localStorage.getItem(CONFIG_KEY);
  if (raw) return JSON.parse(raw) as ConfigStatus;
  localStorage.setItem(CONFIG_KEY, JSON.stringify(configStatus));
  return clone(configStatus);
}

function saveConfig(status: ConfigStatus) {
  localStorage.setItem(CONFIG_KEY, JSON.stringify(status));
}

function makeSession(user: User): AuthSession {
  return {
    user,
    tokens: {
      access_token: `mock.${user.id}.${Date.now()}`,
      refresh_token: `mock.refresh.${user.id}`,
      token_type: "bearer",
      expires_in: 7200,
    },
  };
}

function currentUser(): User | null {
  const raw = localStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  const id = JSON.parse(raw) as string;
  return loadUsers().find((u) => u.id === id) ?? null;
}

function requireUser(): User {
  const user = currentUser();
  if (!user) throw new ApiError("未登录或登录已过期", 401, { code: "UNAUTHENTICATED" });
  if (user.status !== "active") throw new ApiError("账号尚未启用或已停用", 403, { code: "ACCOUNT_INACTIVE" });
  return user;
}

function requireRole(roles: Role[]) {
  const user = requireUser();
  if (!roles.includes(user.role)) throw new ApiError("当前角色无权执行该操作", 403, { code: "FORBIDDEN" });
  return user;
}

let liveTask: Task | null = null;
let liveValidate: ValidateTaskResponse | null = null;
let nodeTimer: number | null = null;

function persistTask(task: Task | null) {
  liveTask = task;
  if (task) localStorage.setItem(TASK_KEY, JSON.stringify(task));
  else localStorage.removeItem(TASK_KEY);
}

function restoreTask() {
  if (liveTask) return liveTask;
  const raw = localStorage.getItem(TASK_KEY);
  if (raw) liveTask = JSON.parse(raw) as Task;
  return liveTask;
}

const NODES = ["node_00", "node_01", "node_02", "node_03", "node_04", "node_05", "node_06"];

function advanceTask() {
  const task = restoreTask();
  if (!task || task.status !== "running") return;
  const done = task.progress.completed_nodes.length;
  if (done >= NODES.length) {
    persistTask({
      ...task,
      status: "completed",
      updated_at: new Date().toISOString(),
      progress: { completed_nodes: NODES, total_nodes: 7, current_node: null },
      quote_summary: clone(completedTask.quote_summary),
      files: clone(completedTask.files),
    });
    return;
  }
  const next = NODES[done];
  persistTask({
    ...task,
    updated_at: new Date().toISOString(),
    progress: {
      completed_nodes: NODES.slice(0, done + 1),
      total_nodes: 7,
      current_node: next,
    },
  });
}

export const api = {
  async login(email: string, password: string): Promise<AuthSession> {
    if (isMockEnabled()) {
      await wait();
      const user = loadUsers().find((u) => u.email === email);
      if (!user || password !== DEMO_PASSWORD) throw new ApiError("邮箱或密码不正确", 401, { code: "INVALID_CREDENTIALS" });
      if (user.status === "pending") throw new ApiError("账号待管理员审核，暂不能登录", 403, { code: "ACCOUNT_PENDING" });
      if (user.status === "disabled") throw new ApiError("账号已停用", 403, { code: "ACCOUNT_DISABLED" });
      const session = makeSession(user);
      localStorage.setItem(SESSION_KEY, JSON.stringify(user.id));
      setTokens(session.tokens.access_token, session.tokens.refresh_token);
      const users = loadUsers().map((u) => (u.id === user.id ? { ...u, last_login_at: new Date().toISOString() } : u));
      saveUsers(users);
      session.user = users.find((u) => u.id === user.id)!;
      return session;
    }
    const session = await request<AuthSession>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }, { auth: false });
    setTokens(session.tokens.access_token, session.tokens.refresh_token);
    return session;
  },

  async register(payload: { email: string; name: string; password: string }): Promise<{ message: string }> {
    if (isMockEnabled()) {
      await wait();
      const users = loadUsers();
      if (users.some((u) => u.email === payload.email)) throw new ApiError("该邮箱已注册", 409, { code: "EMAIL_TAKEN" });
      users.push({
        id: `u_${Date.now()}`,
        email: payload.email,
        name: payload.name,
        role: "operator",
        status: "pending",
        created_at: new Date().toISOString(),
        last_login_at: null,
      });
      saveUsers(users);
      return { message: "注册成功，请等待管理员审核后再登录" };
    }
    return request("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }, { auth: false });
  },

  async me(): Promise<User> {
    if (isMockEnabled()) {
      await wait(80);
      return clone(requireUser());
    }
    return request("/api/v1/auth/me");
  },

  async logout(): Promise<void> {
    if (isMockEnabled()) {
      localStorage.removeItem(SESSION_KEY);
      clearTokens();
      return;
    }
    try {
      await request("/api/v1/auth/logout", { method: "POST" });
    } finally {
      clearTokens();
    }
  },

  async overview(): Promise<DashboardOverview> {
    if (isMockEnabled()) {
      await wait();
      requireUser();
      const task = restoreTask();
      const items = loadExceptions();
      const pending = items.filter((e) => e.status !== "已解决").length;
      if (task?.status === "completed" && task.quote_summary) {
        const details = task.quote_summary.details;
        return {
          latest_task: clone(task),
          task_status_label: "已完成",
          media_count: new Set(details.map((d) => d.media_name)).size,
          quote_count: details.length,
          total_fee: details.reduce((s, d) => s + d.amount, 0),
          type_distribution: ["图文", "视频"].map((type) => ({
            content_type: type,
            quote_count: details.filter((d) => d.content_type === type).length,
          })).filter((row) => row.quote_count > 0),
          pending_exceptions: pending,
          config_ready: loadConfig().all_ready,
        };
      }
      return { ...clone(dashboardOverview), pending_exceptions: pending };
    }
    return request("/api/v1/dashboard/overview");
  },

  async configStatus(): Promise<ConfigStatus> {
    if (isMockEnabled()) {
      await wait(80);
      requireUser();
      return clone(loadConfig());
    }
    return request("/api/v1/config");
  },

  async uploadConfig(kind: ConfigKind, file: File): Promise<ConfigStatus> {
    if (isMockEnabled()) {
      await wait(400);
      const user = requireRole(["admin"]);
      const status = loadConfig();
      status.files = status.files.map((item) =>
        item.kind === kind
          ? { ...item, configured: true, filename: file.name, updated_at: new Date().toISOString(), updated_by: user.id }
          : item,
      );
      status.all_ready = status.files.every((item) => item.configured);
      saveConfig(status);
      return clone(status);
    }
    const body = new FormData();
    body.append("kind", kind);
    body.append("file", file);
    return request("/api/v1/config/files", { method: "POST", body });
  },

  async validateTask(file: File | null): Promise<ValidateTaskResponse> {
    if (isMockEnabled()) {
      await wait(500);
      requireRole(["admin", "operator"]);
      const payload = clone(validateNeedsCorrection);
      payload.task_id = `task_${Date.now()}`;
      liveValidate = payload;
      persistTask({
        task_id: payload.task_id,
        status: "needs_correction",
        filename: file?.name || "1-链接.xlsx（演示）",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        created_by: requireUser().id,
        error: null,
        progress: { completed_nodes: [], total_nodes: 7, current_node: null },
        quote_summary: null,
        files: [],
        issues: payload.issues,
      });
      return payload;
    }
    if (!file) throw new ApiError("请先上传 1-链接.xlsx", 400);
    return request("/api/v1/tasks/validate", {
      method: "POST",
      body: file,
      headers: { "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
    });
  },

  async submitCorrections(taskId: string, corrections: Record<string, string>): Promise<ValidateTaskResponse> {
    if (isMockEnabled()) {
      await wait(360);
      requireRole(["admin", "operator"]);
      const source = liveValidate ?? clone(validateNeedsCorrection);
      const records = source.records.map((row) => {
        const nextName = corrections[String(row.row_number)] ?? row.media_name;
        const matched = mediaLibrary.includes(nextName);
        return {
          ...row,
          media_name: nextName,
          match_status: matched ? "matched" as const : "unmatched" as const,
          suggested_name: matched ? "" : row.suggested_name,
        };
      });
      const unmatched = records.filter((r) => r.match_status === "unmatched");
      const payload: ValidateTaskResponse = {
        task_id: taskId,
        status: unmatched.length ? "needs_correction" : "ready",
        records,
        allowed_media_names: mediaLibrary,
        issues: unmatched.map((row) => ({
          record_id: row.record_id,
          code: "MEDIA_NOT_IN_LIBRARY",
          message: "媒体名称无法匹配媒体库",
          severity: "error" as const,
        })),
      };
      liveValidate = payload;
      const task = restoreTask();
      if (task) persistTask({ ...task, status: payload.status, issues: payload.issues, updated_at: new Date().toISOString() });
      return payload;
    }
    return request(`/api/v1/tasks/${taskId}/corrections`, {
      method: "POST",
      body: JSON.stringify({ media_name_corrections: corrections }),
    });
  },

  async runTask(taskId: string): Promise<{ task_id: string; status: string }> {
    if (isMockEnabled()) {
      await wait(200);
      requireRole(["admin", "operator"]);
      const task = restoreTask();
      if (!task || task.task_id !== taskId) throw new ApiError("任务不存在", 404);
      persistTask({
        ...task,
        status: "running",
        updated_at: new Date().toISOString(),
        progress: { completed_nodes: ["node_00"], total_nodes: 7, current_node: "node_00" },
      });
      if (nodeTimer) window.clearInterval(nodeTimer);
      nodeTimer = window.setInterval(advanceTask, 900);
      return { task_id: taskId, status: "running" };
    }
    return request(`/api/v1/tasks/${taskId}/run`, { method: "POST" });
  },

  async getTask(taskId: string): Promise<Task> {
    if (isMockEnabled()) {
      await wait(120);
      requireUser();
      const task = restoreTask();
      if (!task || task.task_id !== taskId) return clone(completedTask);
      if (task.status === "completed" && nodeTimer) {
        window.clearInterval(nodeTimer);
        nodeTimer = null;
      }
      return clone(task);
    }
    return request(`/api/v1/tasks/${taskId}`);
  },

  async latestTask(): Promise<Task | null> {
    if (isMockEnabled()) {
      await wait(80);
      requireUser();
      return clone(restoreTask() ?? completedTask);
    }
    return request("/api/v1/tasks/latest");
  },

  async quotes(taskId?: string): Promise<{ task: Task | null; details: typeof quoteDetails; demo: boolean }> {
    if (isMockEnabled()) {
      await wait();
      requireUser();
      const task = taskId ? await this.getTask(taskId) : restoreTask();
      if (task?.quote_summary?.details?.length) {
        return { task, details: task.quote_summary.details, demo: false };
      }
      return { task: completedTask, details: quoteDetails, demo: true };
    }
    const task = taskId
      ? await request<Task>(`/api/v1/tasks/${taskId}`)
      : await request<Task | null>("/api/v1/tasks/latest");
    return {
      task,
      details: task?.quote_summary?.details ?? [],
      demo: !task?.quote_summary?.details?.length,
    };
  },

  async monthly(month?: string): Promise<MonthlyAnalytics> {
    if (isMockEnabled()) {
      await wait();
      requireUser();
      return clone(monthlyAnalytics);
    }
    const query = month ? `?month=${encodeURIComponent(month)}` : "";
    return request(`/api/v1/analytics/monthly${query}`);
  },

  async listExceptions(taskId?: string): Promise<ExceptionItem[]> {
    if (isMockEnabled()) {
      await wait();
      requireRole(["admin", "operator"]);
      const items = loadExceptions();
      return clone(taskId ? items.filter((e) => e.task_id === taskId) : items);
    }
    const query = taskId ? `?task_id=${encodeURIComponent(taskId)}` : "";
    return request(`/api/v1/exceptions${query}`);
  },

  async saveException(id: string, summaryFees: Record<string, number>): Promise<ExceptionItem> {
    if (isMockEnabled()) {
      await wait(280);
      requireRole(["admin", "operator"]);
      const items = loadExceptions();
      const index = items.findIndex((e) => e.exception_id === id);
      if (index < 0) throw new ApiError("异常不存在", 404);
      const item = items[index];
      const compare: FeeCompareRow[] = item.compare.map((row) => {
        const summary = summaryFees[row.media_name] ?? row.summary_fee;
        return {
          ...row,
          summary_fee: summary,
          status: summary === row.detail_fee ? "一致" : "不一致",
        };
      });
      const matched = compare.every((row) => row.status === "一致");
      if (!matched) throw new ApiError("请先修改红色金额，确保两个子表中各媒体费用及总费用全部一致。", 400);
      const total = compare.reduce((s, row) => s + row.detail_fee, 0);
      items[index] = {
        ...item,
        compare,
        status: "待校对",
        correction: `两个子表费用已一致，总费用 ¥${total.toLocaleString("zh-CN")}`,
      };
      saveExceptions(items);
      return clone(items[index]);
    }
    return request(`/api/v1/exceptions/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ summary_fees: summaryFees }),
    });
  },

  async reauditExceptions(): Promise<{ resolved: number; remaining: number }> {
    if (isMockEnabled()) {
      await wait(320);
      requireRole(["admin", "operator"]);
      const items = loadExceptions().map((item) =>
        item.status === "待校对" && item.correction ? { ...item, status: "已解决" as const } : item,
      );
      saveExceptions(items);
      const resolved = items.filter((i) => i.status === "已解决").length;
      return { resolved, remaining: items.length - resolved };
    }
    return request("/api/v1/exceptions/reaudit", { method: "POST" });
  },

  async downloadFile(taskId: string, fileKey: string): Promise<Blob> {
    if (isMockEnabled()) {
      await wait(200);
      requireRole(["admin", "operator", "finance"]);
      const text = `Mock file ${fileKey} for ${taskId}`;
      return new Blob([text], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    }
    return requestBlob(`/api/v1/tasks/${taskId}/files/${fileKey}`);
  },

  async downloadAll(taskId: string): Promise<Blob> {
    if (isMockEnabled()) {
      await wait(240);
      requireRole(["admin", "operator", "finance"]);
      return new Blob([`Mock zip for ${taskId}`], { type: "application/zip" });
    }
    return requestBlob(`/api/v1/tasks/${taskId}/files/archive`);
  },

  async listUsers(): Promise<User[]> {
    if (isMockEnabled()) {
      await wait();
      requireRole(["admin"]);
      return clone(loadUsers());
    }
    return request("/api/v1/users");
  },

  async updateUser(id: string, patch: { role?: Role; status?: UserStatus }): Promise<User> {
    if (isMockEnabled()) {
      await wait(200);
      requireRole(["admin"]);
      const users = loadUsers();
      const index = users.findIndex((u) => u.id === id);
      if (index < 0) throw new ApiError("用户不存在", 404);
      users[index] = { ...users[index], ...patch };
      saveUsers(users);
      return clone(users[index]);
    }
    return request(`/api/v1/users/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
  },
};
