import { runtimeConfig } from "../../config";
import { api } from "../../services/api";
import {
  INVALID_INVITATION_MESSAGE,
  invitationErrorMessage,
  mobileSessionErrorMessage,
  projectAccessState,
} from "../../services/login-page.js";

interface InputEvent { detail: { value: string } }
interface PhoneEvent { detail: { code?: string } }

Page({
  data: {
    loggedIn: false,
    invitationToken: "",
    allowInvitationOnlyBinding: runtimeConfig.allowInvitationOnlyBinding,
    phone: "",
    bindingStatus: "",
    busy: false,
    checkingProjects: false,
    hasProjects: false,
    projectCount: 0,
  },
  onLoad(options: Record<string, string | undefined>) {
    const loggedIn = Boolean(wx.getStorageSync("access_token"));
    this.setData({
      loggedIn,
      invitationToken: options.invitation || options.scene || "",
    });
    if (loggedIn) void this.refreshProjectAccess();
  },
  async login() {
    this.setData({ busy: true });
    try {
      const code = runtimeConfig.useDevelopmentLogin
        ? runtimeConfig.developmentLoginCode
        : (await wx.login()).code;
      const result = await api.login(code);
      wx.setStorageSync("access_token", result.access_token);
      this.setData({ loggedIn: true });
      await this.refreshProjectAccess();
    } catch (error) {
      this.showError(error);
    } finally {
      this.setData({ busy: false });
    }
  },
  onTokenInput(event: InputEvent) {
    this.setData({ invitationToken: event.detail.value });
  },
  onPhoneInput(event: InputEvent) {
    this.setData({ phone: event.detail.value });
  },
  async bindWithPhone() {
    await this.acceptInvitation(this.data.phone, undefined);
  },
  async bindWithInvitationOnly() {
    await this.acceptInvitation(undefined, undefined);
  },
  async onGetPhoneNumber(event: PhoneEvent) {
    if (!event.detail.code) {
      wx.showToast({ title: "未取得手机号授权", icon: "none" });
      return;
    }
    await this.acceptInvitation(undefined, event.detail.code);
  },
  async acceptInvitation(phone?: string, phoneCode?: string) {
    if (!this.data.invitationToken) {
      wx.showToast({ title: "请输入邀请令牌", icon: "none" });
      return;
    }
    try {
      const result = await api.acceptInvitation(this.data.invitationToken, phone, phoneCode);
      this.setData({ bindingStatus: result.status });
      if (result.status === "bound") wx.switchTab({ url: "/pages/projects/projects" });
    } catch (error) {
      if (this.resetInvalidMobileSession(error)) return;
      const message = invitationErrorMessage(error);
      if (message === INVALID_INVITATION_MESSAGE) {
        wx.showModal({
          title: "邀请码无效",
          content: message,
          showCancel: false,
        });
        return;
      }
      this.showError(error);
    }
  },
  async refreshProjectAccess() {
    this.setData({ checkingProjects: true });
    try {
      this.setData(projectAccessState(await api.projects()));
    } catch (error) {
      if (this.resetInvalidMobileSession(error)) return;
      this.showError(error);
    } finally {
      this.setData({ checkingProjects: false });
    }
  },
  openProjects() {
    wx.switchTab({ url: "/pages/projects/projects" });
  },
  resetInvalidMobileSession(error: unknown): boolean {
    const message = mobileSessionErrorMessage(error);
    if (!message) return false;
    wx.removeStorageSync("access_token");
    this.setData({ loggedIn: false, hasProjects: false, projectCount: 0 });
    wx.showModal({ title: "请重新登录", content: message, showCancel: false });
    return true;
  },
  showError(error: unknown) {
    wx.showToast({ title: error instanceof Error ? error.message : "操作失败", icon: "none" });
  },
});
