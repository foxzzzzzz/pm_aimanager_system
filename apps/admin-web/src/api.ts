import type {
  AuditLog,
  ChangeProposal,
  Dashboard,
  ImportRecord,
  Issue,
  MemberBinding,
  Project,
  ProjectVersion,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:18000/api/v1";
const TOKEN_KEY = "admin_api_token";

export function setAdminToken(token: string) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearAdminToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

export function hasAdminToken() {
  return Boolean(sessionStorage.getItem(TOKEN_KEY));
}

function requestKey(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = sessionStorage.getItem(TOKEN_KEY);
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = payload?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object" && "message" in detail
          ? String(detail.message)
          : "请求失败，请稍后重试";
    throw Object.assign(new Error(message), { status: response.status });
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
  listMemberBindings: (projectId: string) =>
    request<MemberBinding[]>(`/projects/${projectId}/member-bindings`),
  createMemberInvitation: (
    projectId: string,
    payload: { member_name: string; expected_phone?: string },
  ) =>
    request<MemberBinding & { invitation_token: string }>(
      `/projects/${projectId}/member-invitations`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Idempotency-Key": requestKey("member-invitation"),
        },
        body: JSON.stringify(payload),
      },
    ),
  approveMemberBinding: (bindingId: string) =>
    request<MemberBinding>(`/member-bindings/${bindingId}/approve`, {
      method: "POST",
      headers: { "X-Idempotency-Key": requestKey("binding-approve") },
    }),
  listChangeProposals: (projectId: string) =>
    request<ChangeProposal[]>(`/projects/${projectId}/change-proposals`),
  approveChangeProposal: (proposal: ChangeProposal) =>
    request<ProjectVersion>(`/change-proposals/${proposal.id}/approve`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Idempotency-Key": requestKey("proposal-approve"),
      },
      body: JSON.stringify({ expected_project_version: proposal.base_version_number }),
    }),
  rejectChangeProposal: (proposalId: string, reason: string) =>
    request<ChangeProposal>(`/change-proposals/${proposalId}/reject`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Idempotency-Key": requestKey("proposal-reject"),
      },
      body: JSON.stringify({ reason }),
    }),
};
