import { api } from "../../services/api";
import { runtimeConfig } from "../../config";
import { filterMilestones } from "../../services/milestone-view.js";
import type { ProjectSummary } from "../../types";
import { syncTabBarBadges } from "../../services/tab-badges";

interface ProjectTapEvent {
  currentTarget: { dataset: { id: string; code: string; name: string } };
}

interface ProjectAlertMilestone {
  code: string;
  name: string;
  endDate: string;
  roles: Array<{ key: "R" | "A" | "C" | "I"; names: string }>;
}

interface ProjectSummaryView extends ProjectSummary {
  upcomingMilestones: ProjectAlertMilestone[];
  overdueMilestones: ProjectAlertMilestone[];
}

const presentAlertMilestones = (milestones: ProjectSummary["milestones"]): ProjectAlertMilestone[] =>
  milestones.map((milestone) => ({
    code: milestone.code,
    name: milestone.name,
    endDate: milestone.plan?.end_date || "—",
    roles: (["R", "A", "C", "I"] as const).map((key) => ({
      key,
      names: milestone.assignments[key]?.join("、") || "—",
    })),
  }));

const presentProjects = (projects: ProjectSummary[]): ProjectSummaryView[] => projects.map(
  (project) => ({
    ...project,
    upcomingMilestones: presentAlertMilestones(filterMilestones(
      project.milestones,
      "upcoming",
      project.business_date,
      runtimeConfig.milestoneUpcomingDays,
    )),
    overdueMilestones: presentAlertMilestones(filterMilestones(
      project.milestones,
      "overdue",
      project.business_date,
      runtimeConfig.milestoneUpcomingDays,
    )),
  }),
);

Page({
  data: { projects: [] as ProjectSummaryView[], loading: true, loadError: false },
  async onShow() {
    if (!wx.getStorageSync("access_token")) {
      wx.redirectTo({ url: "/pages/index/index" });
      return;
    }
    await this.loadProjects();
  },
  async loadProjects() {
    this.setData({ loading: true, loadError: false });
    try {
      this.setData({ projects: presentProjects(await api.projects()), loadError: false });
      void syncTabBarBadges();
    } catch {
      this.setData({ loadError: true });
    } finally {
      this.setData({ loading: false });
    }
  },
  openProject(event: ProjectTapEvent) {
    const { id: projectId, code, name } = event.currentTarget.dataset;
    wx.setStorageSync("current_project_id", projectId);
    wx.setStorageSync("current_project_code", code);
    wx.setStorageSync("current_project_name", name);
    wx.navigateTo({ url: `/pages/dashboard/dashboard?projectId=${projectId}` });
  },
});
