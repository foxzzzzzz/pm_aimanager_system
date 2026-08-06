import { api } from "../../services/api";
import type { MobileDashboard } from "../../types";
import type { ChangeProposal } from "../../types";

interface MilestoneTapEvent { currentTarget: { dataset: { code: string } } }
interface ProposalTapEvent { currentTarget: { dataset: { id: string; version: number } } }

Page({
  data: {
    projectId: "",
    dashboard: null as MobileDashboard | null,
    proposals: [] as ChangeProposal[],
    loading: true,
  },
  async onLoad(options: Record<string, string | undefined>) {
    const projectId = options.projectId || wx.getStorageSync<string>("current_project_id");
    this.setData({ projectId });
    try {
      const [dashboard, proposals] = await Promise.all([
        api.dashboard(projectId),
        api.approvableProposals(projectId),
      ]);
      this.setData({ dashboard, proposals });
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
  async approveProposal(event: ProposalTapEvent) {
    try {
      await api.approveProposal(
        event.currentTarget.dataset.id,
        event.currentTarget.dataset.version,
      );
      const [dashboard, proposals] = await Promise.all([
        api.dashboard(this.data.projectId),
        api.approvableProposals(this.data.projectId),
      ]);
      this.setData({ dashboard, proposals });
      wx.showToast({ title: "已批准", icon: "success" });
    } catch (reason) {
      wx.showToast({ title: (reason as Error).message, icon: "none" });
    }
  },
});
