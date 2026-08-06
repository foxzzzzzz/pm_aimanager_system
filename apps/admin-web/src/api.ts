import type {
  AuditLog,
  Dashboard,
  ImportRecord,
  Issue,
  Project,
  ProjectVersion,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:18000/api/v1";
const ACTOR_ID = import.meta.env.VITE_ACTOR_ID ?? "pm-001";

function requestKey(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "X-Actor-Id": ACTOR_ID,
      ...options.headers,
    },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "请求失败，请稍后重试");
  }
  return (await response.json()) as T;
}

export const api = {
  listProjects: () => request<Project[]>("/projects"),
  createProject: (payload: { code: string; name: string }) =>
    request<Project>("/projects", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Idempotency-Key": requestKey("project"),
      },
      body: JSON.stringify(payload),
    }),
  dashboard: (projectId: string) => request<Dashboard>(`/projects/${projectId}/dashboard`),
  uploadImport: (projectId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportRecord>(`/projects/${projectId}/imports`, {
      method: "POST",
      headers: { "X-Idempotency-Key": requestKey("import") },
      body: form,
    });
  },
  publishImport: (record: ImportRecord) =>
    request<ProjectVersion>(`/imports/${record.id}/publish`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Idempotency-Key": requestKey("publish"),
      },
      body: JSON.stringify({ expected_project_version: record.base_version_number }),
    }),
  listVersions: (projectId: string) =>
    request<ProjectVersion[]>(`/projects/${projectId}/versions`),
  listIssues: (projectId: string) => request<Issue[]>(`/projects/${projectId}/issues`),
  createIssue: (
    projectId: string,
    payload: {
      description: string;
      impact: string;
      owner_name: string;
      severity: string;
      due_date: string;
    },
  ) =>
    request<Issue>(`/projects/${projectId}/issues`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Idempotency-Key": requestKey("issue"),
      },
      body: JSON.stringify(payload),
    }),
  listAuditLogs: (projectId: string) =>
    request<AuditLog[]>(`/projects/${projectId}/audit-logs`),
};
