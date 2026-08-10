import { runtimeConfig } from "../../config";
import { api } from "../../services/api";

interface InputEvent { detail: { value: string } }
interface PhoneEvent { detail: { code?: string } }

Page({
  data: {
    loggedIn: false,
    invitationToken: "",
    phone: "",
    bindingStatus: "",
    busy: false,
  },
  onLoad(options: Record<string, string | undefined>) {
    this.setData({
      loggedIn: Boolean(wx.getStorageSync("access_token")),
      invitationToken: options.invitation || options.scene || "",
    });
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
      if (!this.data.invitationToken) wx.switchTab({ url: "/pages/projects/projects" });
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
      this.showError(error);
    }
  },
  showError(error: unknown) {
    wx.showToast({ title: error instanceof Error ? error.message : "操作失败", icon: "none" });
  },
});
