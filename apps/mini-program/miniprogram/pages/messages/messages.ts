import { api } from "../../services/api";
import type { Message } from "../../types";
import { runtimeConfig } from "../../config";
import { formatDateTime, labelMessageType } from "../../services/presentation.js";

interface MessageTapEvent { currentTarget: { dataset: { id: string } } }

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
  data: { messages: [] as MessageView[], subscriptionConfigured, loading: true },
  async onShow() {
    this.setData({ loading: true });
    try {
      this.setData({ messages: presentMessages(await api.messages()) });
    } catch {
      wx.showToast({ title: "消息加载失败", icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },
  async markRead(event: MessageTapEvent) {
    try {
      await api.markMessageRead(event.currentTarget.dataset.id);
      this.setData({ messages: presentMessages(await api.messages()) });
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
