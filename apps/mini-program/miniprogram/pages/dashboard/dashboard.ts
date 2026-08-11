import { api } from "../../services/api";
import { runtimeConfig } from "../../config";
import {
  buildMilestoneFilters,
  filterMilestones,
} from "../../services/milestone-view.js";
import { labelPlanState, presentPlan } from "../../services/presentation.js";
import type { MilestoneFilterKey } from "../../services/milestone-view.js";
import type { ChangeProposal, Milestone, MobileDashboard } from "../../types";

interface MilestoneTapEvent { currentTarget: { dataset: { code: string } } }
interface ProposalTapEvent { currentTarget: { dataset: { id: string; version: number } } }
interface FilterTapEvent { currentTarget: { dataset: { key: MilestoneFilterKey } } }

interface MilestoneView extends Milestone {
  planLabel: string;
  statusLabel: string;
}

const presentMilestones = (milestones: Milestone[]): MilestoneView[] => milestones.map((item) => ({
  ...item,
  planLabel: presentPlan(item.plan),
  statusLabel: item.actual_completion.end_date
    ? "已完成"
    : item.plan && item.plan.state !== "scheduled"
      ? labelPlanState(item.plan.state)
      : "",
}));

Page({
  data: {
    projectId: "",
    dashboard: null as MobileDashboard | null,
    proposals: [] as ChangeProposal[],
    milestoneFilters: [] as ReturnType<typeof buildMilestoneFilters>,
    visibleMilestones: [] as MilestoneView[],
    selectedMilestoneFilter: "todo" as MilestoneFilterKey,
    loading: true,
    loadError: false,
    resolvingProposalId: "",
  },
  onLoad(options: Record<string, string | undefined>) {
    const projectId = options.projectId || wx.getStorageSync<string>("current_project_id");
    this.setData({ projectId });
  },
  async onShow() {
    if (this.data.projectId) await this.loadDashboard();
  },
  async onPullDownRefresh() {
    await this.loadDashboard();
    wx.stopPullDownRefresh();
  },
  async loadDashboard(showError = true): Promise<boolean> {
    if (!this.data.dashboard) this.setData({ loading: true, loadError: false });
    try {
      const [dashboard, proposals] = await Promise.all([
        api.dashboard(this.data.projectId),
        api.approvableProposals(this.data.projectId),
      ]);
      const today = dashboard.business_date;
      const upcomingDays = runtimeConfig.milestoneUpcomingDays;
      this.setData({
        dashboard,
        proposals,
        milestoneFilters: buildMilestoneFilters(dashboard.milestones, today, upcomingDays),
        visibleMilestones: presentMilestones(
          filterMilestones(
            dashboard.milestones,
            this.data.selectedMilestoneFilter,
            today,
            upcomingDays,
          ),
        ),
        loadError: false,
      });
      wx.setStorageSync("current_member_name", dashboard.member_name);
      return true;
    } catch {
      this.setData({ loadError: true });
      if (showError) wx.showToast({ title: "看板加载失败", icon: "none" });
      return false;
    } finally {
      this.setData({ loading: false });
    }
  },
  selectMilestoneFilter(event: FilterTapEvent) {
    if (!this.data.dashboard) return;
    const selectedMilestoneFilter = event.currentTarget.dataset.key;
    this.setData({
      selectedMilestoneFilter,
      visibleMilestones: presentMilestones(
        filterMilestones(
          this.data.dashboard.milestones,
          selectedMilestoneFilter,
          this.data.dashboard.business_date,
          runtimeConfig.milestoneUpcomingDays,
        ),
      ),
    });
  },
  openProjectReview() {
    wx.navigateTo({
      url: `/pages/project-review/project-review?projectId=${this.data.projectId}`,
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
    const confirmation = await wx.showModal({
      title: "批准节点变更",
      content: "批准后将发布新的正式项目版本，是否继续？",
      confirmText: "确认批准",
    });
    if (!confirmation.confirm) return;
    this.setData({ resolvingProposalId: event.currentTarget.dataset.id });
    try {
      await api.approveProposal(
        event.currentTarget.dataset.id,
        event.currentTarget.dataset.version,
      );
      this.setData({
        proposals: this.data.proposals.filter(
          (item) => item.id !== event.currentTarget.dataset.id,
        ),
      });
      const refreshed = await this.loadDashboard(false);
      wx.showToast({
        title: refreshed ? "已批准" : "已批准，请稍后刷新",
        icon: refreshed ? "success" : "none",
      });
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
      this.setData({
        proposals: this.data.proposals.filter(
          (item) => item.id !== event.currentTarget.dataset.id,
        ),
      });
      const refreshed = await this.loadDashboard(false);
      wx.showToast({
        title: refreshed ? "已驳回" : "已驳回，请稍后刷新",
        icon: refreshed ? "success" : "none",
      });
    } catch (error) {
      wx.showToast({ title: (error as Error).message, icon: "none" });
    } finally {
      this.setData({ resolvingProposalId: "" });
    }
  },
});
