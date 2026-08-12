import { api } from "../../services/api";
import { runtimeConfig } from "../../config";
import {
  buildMilestoneFilters,
  filterMilestones,
} from "../../services/milestone-view.js";
import { formatDateTime, labelPlanState, presentPlan } from "../../services/presentation.js";
import type { MilestoneFilterKey } from "../../services/milestone-view.js";
import type { ChangeProposal, IssueCreateProposal, IssueDeleteProposal, Milestone, MobileDashboard } from "../../types";

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
    issueCreateProposals: [] as IssueCreateProposal[],
    issueDeleteProposals: [] as IssueDeleteProposal[],
    milestoneFilters: [] as ReturnType<typeof buildMilestoneFilters>,
    primaryMilestoneFilters: [] as ReturnType<typeof buildMilestoneFilters>,
    moreFilterLabel: "更多筛选",
    visibleMilestones: [] as MilestoneView[],
    selectedMilestoneFilter: "todo" as MilestoneFilterKey,
    loading: true,
    loadError: false,
    resolvingProposalId: "",
    resolvingIssueProposalId: "",
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
      const dashboard = await api.dashboard(this.data.projectId);
      const [proposals, issueCreateProposals, issueDeleteProposals] = await Promise.all([
        api.approvableProposals(this.data.projectId).catch(() => [] as ChangeProposal[]),
        dashboard.is_project_manager
          ? api.issueCreateProposals(this.data.projectId)
          : Promise.resolve([] as IssueCreateProposal[]),
        dashboard.is_project_manager
          ? api.issueDeleteProposals(this.data.projectId)
          : Promise.resolve([] as IssueDeleteProposal[]),
      ]);
      const today = dashboard.business_date;
      const upcomingDays = runtimeConfig.milestoneUpcomingDays;
      const milestoneFilters = buildMilestoneFilters(dashboard.milestones, today, upcomingDays);
      this.setData({
        dashboard,
        proposals: proposals.map((item) => ({
          ...item,
          createdAtLabel: formatDateTime(
            item.created_at,
            runtimeConfig.presentationTimezoneOffsetMinutes,
          ),
        })),
        issueCreateProposals: issueCreateProposals.map((item) => ({
          ...item,
          createdAtLabel: formatDateTime(
            item.created_at,
            runtimeConfig.presentationTimezoneOffsetMinutes,
          ),
        })),
        issueDeleteProposals: issueDeleteProposals.map((item) => ({
          ...item,
          createdAtLabel: formatDateTime(
            item.created_at,
            runtimeConfig.presentationTimezoneOffsetMinutes,
          ),
        })),
        milestoneFilters,
        primaryMilestoneFilters: milestoneFilters.filter(
          (filter) => ["todo", "upcoming", "overdue"].includes(filter.key),
        ),
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
  async resolveIssueCreateProposal(event: WechatMiniprogram.TouchEvent) {
    const id = event.currentTarget.dataset.id as string;
    const action = event.currentTarget.dataset.action as "approve" | "reject";
    if (this.data.resolvingIssueProposalId) return;
    this.setData({ resolvingIssueProposalId: id });
    try {
      if (action === "approve") {
        await api.approveIssueCreateProposal(id);
      } else {
        await api.rejectIssueCreateProposal(id, "项目经理驳回");
      }
      await this.loadDashboard();
      wx.showToast({ title: action === "approve" ? "审批已通过" : "申请已驳回", icon: "success" });
    } catch (error) {
      wx.showToast({ title: (error as Error).message, icon: "none" });
    } finally {
      this.setData({ resolvingIssueProposalId: "" });
    }
  },
  async resolveIssueDeleteProposal(event: WechatMiniprogram.TouchEvent) {
    const id = event.currentTarget.dataset.id as string;
    const action = event.currentTarget.dataset.action as "approve" | "reject";
    if (this.data.resolvingIssueProposalId) return;
    this.setData({ resolvingIssueProposalId: id });
    try {
      if (action === "approve") {
        await api.approveIssueDeleteProposal(id);
      } else {
        await api.rejectIssueDeleteProposal(id, "项目经理驳回");
      }
      await this.loadDashboard();
      wx.showToast({ title: action === "approve" ? "审批已通过" : "申请已驳回", icon: "success" });
    } catch (error) {
      wx.showToast({ title: (error as Error).message, icon: "none" });
    } finally {
      this.setData({ resolvingIssueProposalId: "" });
    }
  },
  selectMilestoneFilter(event: FilterTapEvent) {
    if (!this.data.dashboard) return;
    const selectedMilestoneFilter = event.currentTarget.dataset.key;
    this.setData({
      selectedMilestoneFilter,
      moreFilterLabel: "更多筛选",
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
  async openMoreFilters() {
    const itemList = ["已完成", "全部"];
    try {
      const result = await wx.showActionSheet({ itemList });
      const selectedMilestoneFilter = result.tapIndex === 0 ? "completed" : "all";
      const selectedFilter = this.data.milestoneFilters.find(
        (filter) => filter.key === selectedMilestoneFilter,
      );
      this.setData({
        selectedMilestoneFilter,
        moreFilterLabel: `${selectedFilter?.label || itemList[result.tapIndex]} ${selectedFilter?.count || 0}`,
        visibleMilestones: presentMilestones(
          filterMilestones(
            this.data.dashboard?.milestones || [],
            selectedMilestoneFilter,
            this.data.dashboard?.business_date || "",
            runtimeConfig.milestoneUpcomingDays,
          ),
        ),
      });
    } catch {
      // The user dismissed the action sheet.
    }
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
