import { api } from "../../services/api";
import type { Message } from "../../types";

interface MessageTapEvent { currentTarget: { dataset: { id: string } } }

Page({
  data: { messages: [] as Message[] },
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
});
