import type {
  AuthSession,
  ConfigKind,
  ConfigStatus,
  DashboardOverview,
  ExceptionItem,
  MonthlyAnalytics,
  QuoteDetail,
  Role,
  Task,
  User,
  UserStatus,
  ValidateTaskResponse,
} from "../types";
import { request, requestBlob, setTokens, clearTokens } from "./client";

export const api = {
  async login(email: string, password: string): Promise<AuthSession> {
    const session = await request<AuthSession>(
      "/api/v1/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
      { auth: false },
    );
    setTokens(session.tokens.access_token, session.tokens.refresh_token);
    return session;
  },

  async register(payload: { email: string; name: string; password: string }): Promise<{ message: string }> {
    return request(
      "/api/v1/auth/register",
      { method: "POST", body: JSON.stringify(payload) },
      { auth: false },
    );
  },

  async me(): Promise<User> {
    return request("/api/v1/auth/me");
  },

  async logout(): Promise<void> {
    try {
      await request("/api/v1/auth/logout", { method: "POST" });
    } finally {
      clearTokens();
    }
  },

  async overview(): Promise<DashboardOverview> {
    return request("/api/v1/dashboard/overview");
  },

  async configStatus(): Promise<ConfigStatus> {
    return request("/api/v1/config");
  },

  async uploadConfig(kind: ConfigKind, file: File): Promise<ConfigStatus> {
    const body = new FormData();
    body.append("kind", kind);
    body.append("file", file);
    return request("/api/v1/config/files", { method: "POST", body });
  },

  async validateTask(file: File): Promise<ValidateTaskResponse> {
    return request("/api/v1/tasks/validate", {
      method: "POST",
      body: file,
      headers: {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      },
    });
  },

  async submitCorrections(taskId: string, corrections: Record<string, string>): Promise<ValidateTaskResponse> {
    return request(`/api/v1/tasks/${taskId}/corrections`, {
      method: "POST",
      body: JSON.stringify({ media_name_corrections: corrections }),
    });
  },

  async submitPublicationCorrections(
    taskId: string,
    corrections: Record<string, { title: string; article_type: string }>,
  ): Promise<{ task_id: string; status: string }> {
    return request(`/api/v1/tasks/${taskId}/publication-corrections`, {
      method: "POST",
      body: JSON.stringify({ corrections }),
    });
  },

  async runTask(taskId: string): Promise<{ task_id: string; status: string }> {
    return request(`/api/v1/tasks/${taskId}/run`, { method: "POST" });
  },

  async getTask(taskId: string): Promise<Task> {
    return request(`/api/v1/tasks/${taskId}`);
  },

  async latestTask(): Promise<Task | null> {
    return request("/api/v1/tasks/latest");
  },

  async listTasks(): Promise<Task[]> {
    return request("/api/v1/tasks");
  },

  async quotes(): Promise<{ task: Task | null; details: QuoteDetail[] }> {
    const task = await request<Task | null>("/api/v1/tasks/latest");
    return {
      task,
      details: task?.status === "completed" ? task.quote_summary?.details ?? [] : [],
    };
  },

  async monthly(month?: string): Promise<MonthlyAnalytics> {
    const query = month ? `?month=${encodeURIComponent(month)}` : "";
    return request(`/api/v1/analytics/monthly${query}`);
  },

  async listExceptions(taskId?: string): Promise<ExceptionItem[]> {
    const query = taskId ? `?task_id=${encodeURIComponent(taskId)}` : "";
    return request(`/api/v1/exceptions${query}`);
  },

  async saveException(id: string, summaryFees: Record<string, number>): Promise<ExceptionItem> {
    return request(`/api/v1/exceptions/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ summary_fees: summaryFees }),
    });
  },

  async reauditExceptions(): Promise<{ resolved: number; remaining: number }> {
    return request("/api/v1/exceptions/reaudit", { method: "POST" });
  },

  async downloadFile(taskId: string, fileKey: string): Promise<Blob> {
    return requestBlob(`/api/v1/tasks/${taskId}/files/${fileKey}`);
  },

  async downloadAll(taskId: string): Promise<Blob> {
    return requestBlob(`/api/v1/tasks/${taskId}/files/archive`);
  },

  async listUsers(): Promise<User[]> {
    return request("/api/v1/users");
  },

  async updateUser(id: string, patch: { role?: Role; status?: UserStatus }): Promise<User> {
    return request(`/api/v1/users/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
  },
};
