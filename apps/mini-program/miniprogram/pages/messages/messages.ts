import { api } from "../../services/api";
import type { Message } from "../../types";

Page({
  data: { messages: [] as Message[] },
  async onShow() {
    try {
      this.setData({ messages: await api.messages() });
    } catch {
      wx.showToast({ title: "消息加载失败", icon: "none" });
    }
  },
});
