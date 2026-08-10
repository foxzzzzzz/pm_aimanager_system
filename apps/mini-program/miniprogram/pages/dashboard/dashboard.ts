import { api } from "../../services/api";
import { runtimeConfig } from "../../config";
import {
  buildMilestoneFilters,
  filterMilestones,
} from "../../services/milestone-view.js";
import type { MilestoneFilterKey } from "../../services/milestone-view.js";
import type { ChangeProposal, Milestone, MobileDashboard } from "../../types";

interface MilestoneTapEvent { currentTarget: { dataset: { code: string } } }
interface ProposalTapEvent { currentTarget: { dataset: { id: string; version: number } } }
interface FilterTapEvent { currentTarget: { dataset: { key: MilestoneFilterKey } } }

const localDateText = () => {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
};

Page({
  data: {
    projectId: "",
    dashboard: null as MobileDashboard | null,
    proposals: [] as ChangeProposal[],
    milestoneFilters: [] as ReturnType<typeof buildMilestoneFilters>,
    visibleMilestones: [] as Milestone[],
    selectedMilestoneFilter: "todo" as MilestoneFilterKey,
    loading: true,
    resolvingProposalId: "",
  },
  async onLoad(options: Record<string, string | undefined>) {
    const projectId = options.projectId || wx.getStorageSync<string>("current_project_id");
    this.setData({ projectId });
    await this.loadDashboard();
  },
  async loadDashboard() {
    try {
      const [dashboard, proposals] = await Promise.all([
        api.dashboard(this.data.projectId),
        api.approvableProposals(this.data.projectId),
      ]);
      const today = localDateText();
      const upcomingDays = runtimeConfig.milestoneUpcomingDays;
      this.setData({
        dashboard,
        proposals,
        milestoneFilters: buildMilestoneFilters(dashboard.milestones, today, upcomingDays),
        visibleMilestones: filterMilestones(
          dashboard.milestones,
          this.data.selectedMilestoneFilter,
          today,
          upcomingDays,
        ),
      });
      wx.setStorageSync("current_member_name", dashboard.member_name);
    } catch {
      wx.showToast({ title: "看板加载失败", icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },
  selectMilestoneFilter(event: FilterTapEvent) {
    if (!this.data.dashboard) return;
    const selectedMilestoneFilter = event.currentTarget.dataset.key;
    this.setData({
      selectedMilestoneFilter,
      visibleMilestones: filterMilestones(
        this.data.dashboard.milestones,
        selectedMilestoneFilter,
        localDateText(),
        runtimeConfig.milestoneUpcomingDays,
      ),
    });
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
    if (this.data.resolvingProposalId) return;
    this.setData({ resolvingProposalId: event.currentTarget.dataset.id });
    try {
      await api.approveProposal(
        event.currentTarget.dataset.id,
        event.currentTarget.dataset.version,
      );
      await this.loadDashboard();
      wx.showToast({ title: "已批准", icon: "success" });
    } catch (reason) {
      wx.showToast({ title: (reason as Error).message, icon: "none" });
    } finally {
      this.setData({ resolvingProposalId: "" });
    }
  },
  async rejectProposal(event: ProposalTapEvent) {
    if (this.data.resolvingProposalId) return;
    const confirmation = await wx.showModal({
      title: "驳回节点变更",
      content: "请输入驳回原因",
      editable: true,
      placeholderText: "驳回原因（必填）",
      confirmText: "确认驳回",
      confirmColor: "#c53030",
    });
    const reason = confirmation.content?.trim();
    if (!confirmation.confirm || !reason) return;
    this.setData({ resolvingProposalId: event.currentTarget.dataset.id });
    try {
      await api.rejectProposal(event.currentTarget.dataset.id, reason);
      await this.loadDashboard();
      wx.showToast({ title: "已驳回", icon: "success" });
    } catch (error) {
      wx.showToast({ title: (error as Error).message, icon: "none" });
    } finally {
      this.setData({ resolvingProposalId: "" });
    }
  },
});
