import { runtimeConfig } from "../config";
import type {
  ChangeProposal,
  Issue,
  Message,
  MobileDashboard,
  ProjectReview,
  ProjectSummary,
} from "../types";
import { createRequester } from "./request-core.js";

function requestKey(): string {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

const request = createRequester({
  baseUrl: runtimeConfig.apiBaseUrl,
  getToken: () => wx.getStorageSync<string>("access_token"),
  requestKey,
  retryAttempts: runtimeConfig.requestRetryAttempts,
  transport: (options: WechatMiniprogram.RequestOption) => { wx.request(options); },
});

export const api = {
  login: (code: string) =>
    request<{ access_token: string }>("/mobile/auth/wechat", "POST", {
      code,
      display_name: "微信用户",
    }),
  acceptInvitation: (invitationToken: string, phone?: string, phoneCode?: string) =>
    request<{ status: string }>("/mobile/invitations/accept", "POST", {
      invitation_token: invitationToken,
      phone,
      phone_code: phoneCode,
    }),
  projects: () => request<ProjectSummary[]>("/mobile/projects"),
  dashboard: (projectId: string) =>
    request<MobileDashboard>(`/mobile/projects/${projectId}/dashboard`),
  projectReview: (projectId: string) =>
    request<ProjectReview>(`/mobile/projects/${projectId}/review`),
  submitMilestone: (projectId: string, code: string, data: WechatMiniprogram.IAnyObject) =>
    request(`/mobile/projects/${projectId}/milestones/${code}/proposals`, "POST", data),
  issues: (projectId: string) => request<Issue[]>(`/mobile/projects/${projectId}/issues`),
  createIssue: (projectId: string, data: WechatMiniprogram.IAnyObject) =>
    request<Issue>(`/mobile/projects/${projectId}/issues`, "POST", data),
  updateIssue: (issueId: string, data: WechatMiniprogram.IAnyObject) =>
    request<Issue>(`/mobile/issues/${issueId}`, "PATCH", data),
  deleteIssue: (issueId: string, data: WechatMiniprogram.IAnyObject) =>
    request<Issue>(`/mobile/issues/${issueId}`, "DELETE", data),
  approvableProposals: (projectId: string) =>
    request<ChangeProposal[]>(`/mobile/projects/${projectId}/change-proposals`),
  approveProposal: (proposalId: string, expectedVersion: number) =>
    request(`/mobile/change-proposals/${proposalId}/approve`, "POST", {
      expected_project_version: expectedVersion,
    }),
  rejectProposal: (proposalId: string, reason: string) =>
    request(`/mobile/change-proposals/${proposalId}/reject`, "POST", { reason }),
  messages: () => request<Message[]>("/mobile/messages"),
  markMessageRead: (messageId: string) =>
    request<Message>(`/mobile/messages/${messageId}/read`, "PATCH"),
  registerSubscriptionGrant: (templateId: string) =>
    request<{ template_id: string; remaining_uses: number }>(
      "/mobile/subscription-grants",
      "POST",
      { template_id: templateId },
    ),
  prefill: (text: string) =>
    request<{
      milestone_code: string | null;
      kind: "delay" | null;
      start_date: string | null;
      end_date: string | null;
      reason: string;
      requires_confirmation: boolean;
    }>("/mobile/natural-language/prefill", "POST", { text }),
};
