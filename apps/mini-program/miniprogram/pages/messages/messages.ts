import { api } from "../../services/api";
import type { Message } from "../../types";
import { runtimeConfig } from "../../config";

interface MessageTapEvent { currentTarget: { dataset: { id: string } } }

const subscriptionConfigured = runtimeConfig.subscriptionTemplateId !== "replace-with-template-id";

Page({
  data: { messages: [] as Message[], subscriptionConfigured },
  async onShow() {
    try {
      this.setData({ messages: await api.messages() });
    } catch {
      wx.showToast({ title: "消息加载失败", icon: "none" });
    }
  },
  async markRead(event: MessageTapEvent) {
    try {
      await api.markMessageRead(event.currentTarget.dataset.id);
      this.setData({ messages: await api.messages() });
    } catch (reason) {
      wx.showToast({ title: (reason as Error).message, icon: "none" });
    }
  },
  async enableReminder() {
    if (!this.data.subscriptionConfigured) {
      wx.showToast({ title: "微信提醒模板暂未配置", icon: "none" });
      return;
    }
    try {
      const templateId = runtimeConfig.subscriptionTemplateId;
      const result = await wx.requestSubscribeMessage({ tmplIds: [templateId] });
      if (result[templateId] !== "accept") {
        wx.showToast({ title: "未授权消息提醒", icon: "none" });
        return;
      }
      await api.registerSubscriptionGrant(templateId);
      wx.showToast({ title: "提醒已开启", icon: "success" });
    } catch (reason) {
      wx.showToast({ title: (reason as Error).message, icon: "none" });
    }
  },
});
