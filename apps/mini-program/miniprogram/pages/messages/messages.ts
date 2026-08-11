import { api } from "../../services/api";
import type { Message } from "../../types";
import { runtimeConfig } from "../../config";
import { formatDateTime, labelMessageType } from "../../services/presentation.js";

interface MessageTapEvent { currentTarget: { dataset: { id: string; read: boolean } } }

const subscriptionConfigured = runtimeConfig.subscriptionTemplateId !== "replace-with-template-id";

interface MessageView extends Message {
  typeLabel: string;
  createdAtLabel: string;
}

const presentMessages = (messages: Message[]): MessageView[] => messages.map((message) => ({
  ...message,
  typeLabel: labelMessageType(message.type),
  createdAtLabel: formatDateTime(
    message.created_at,
    runtimeConfig.presentationTimezoneOffsetMinutes,
  ),
}));

Page({
  data: {
    messages: [] as MessageView[],
    subscriptionConfigured,
    loading: true,
    loadError: false,
  },
  async onShow() {
    await this.loadMessages();
  },
  async loadMessages() {
    this.setData({ loading: true, loadError: false });
    try {
      this.setData({ messages: presentMessages(await api.messages()), loadError: false });
    } catch {
      this.setData({ loadError: true });
    } finally {
      this.setData({ loading: false });
    }
  },
  async markRead(event: MessageTapEvent) {
    if (event.currentTarget.dataset.read) return;
    try {
      const saved = await api.markMessageRead(event.currentTarget.dataset.id);
      this.setData({
        messages: this.data.messages.map((message) => message.id === saved.id
          ? presentMessages([saved])[0]
          : message),
      });
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
