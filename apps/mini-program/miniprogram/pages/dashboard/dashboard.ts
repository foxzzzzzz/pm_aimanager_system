import { api } from "../../services/api";
import type { MobileDashboard } from "../../types";

interface MilestoneTapEvent { currentTarget: { dataset: { code: string } } }

Page({
  data: { projectId: "", dashboard: null as MobileDashboard | null, loading: true },
  async onLoad(options: Record<string, string | undefined>) {
    const projectId = options.projectId || wx.getStorageSync<string>("current_project_id");
    this.setData({ projectId });
    try {
      this.setData({ dashboard: await api.dashboard(projectId) });
    } catch {
      wx.showToast({ title: "看板加载失败", icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },
  updateMilestone(event: MilestoneTapEvent) {
    if (!this.data.dashboard) return;
    wx.navigateTo({
      url:
        `/pages/milestone-update/milestone-update?projectId=${this.data.projectId}`
        + `&code=${event.currentTarget.dataset.code}`
        + `&version=${this.data.dashboard.current_version_number}`,
    });
  },
});
