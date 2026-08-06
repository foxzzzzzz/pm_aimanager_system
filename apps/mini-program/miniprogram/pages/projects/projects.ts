import { api } from "../../services/api";
import type { ProjectSummary } from "../../types";

interface ProjectTapEvent { currentTarget: { dataset: { id: string } } }

Page({
  data: { projects: [] as ProjectSummary[], loading: true },
  async onShow() {
    if (!wx.getStorageSync("access_token")) {
      wx.redirectTo({ url: "/pages/index/index" });
      return;
    }
    try {
      this.setData({ projects: await api.projects() });
    } catch {
      wx.showToast({ title: "项目加载失败", icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },
  openProject(event: ProjectTapEvent) {
    const projectId = event.currentTarget.dataset.id;
    wx.setStorageSync("current_project_id", projectId);
    wx.navigateTo({ url: `/pages/dashboard/dashboard?projectId=${projectId}` });
  },
});
