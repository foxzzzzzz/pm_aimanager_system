import { runtimeConfig } from "../config";
import type { Issue, Message, MobileDashboard, ProjectSummary } from "../types";

type Method = "GET" | "POST";

function request<T>(
  path: string,
  method: Method = "GET",
  data?: WechatMiniprogram.IAnyObject,
): Promise<T> {
  const accessToken = wx.getStorageSync<string>("access_token");
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${runtimeConfig.apiBaseUrl}${path}`,
      method,
      data,
      header: {
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...(method !== "GET" ? { "X-Idempotency-Key": requestKey() } : {}),
      },
      success: (response) => {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.data as unknown as T);
        } else {
          reject(new Error(`请求失败：${response.statusCode}`));
        }
      },
      fail: reject,
    });
  });
}

function requestKey(): string {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

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
  submitMilestone: (projectId: string, code: string, data: WechatMiniprogram.IAnyObject) =>
    request(`/mobile/projects/${projectId}/milestones/${code}/proposals`, "POST", data),
  issues: (projectId: string) => request<Issue[]>(`/mobile/projects/${projectId}/issues`),
  createIssue: (projectId: string, data: WechatMiniprogram.IAnyObject) =>
    request<Issue>(`/mobile/projects/${projectId}/issues`, "POST", data),
  messages: () => request<Message[]>("/mobile/messages"),
  prefill: (text: string) =>
    request<{
      milestone_code: string | null;
      kind: "delay" | null;
      end_date: string | null;
      reason: string;
      requires_confirmation: boolean;
    }>("/mobile/natural-language/prefill", "POST", { text }),
};
