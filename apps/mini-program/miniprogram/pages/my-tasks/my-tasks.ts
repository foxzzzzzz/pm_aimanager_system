import { api } from "../../services/api";
import type { MyTask, MyTaskProject } from "../../types";
import { syncTabBarBadges } from "../../services/tab-badges";

type TaskFilter = "todo" | "upcoming" | "overdue" | "completed";

interface ProjectTaskView extends MyTaskProject {
  visibleTasks: MyTask[];
  entryLabel: string;
  focusIssueId: string;
}

interface FilterTapEvent {
  currentTarget: { dataset: { key: TaskFilter } };
}

interface ProjectTapEvent {
  currentTarget: {
    dataset: { id: string; code: string; name: string; focusIssueId: string };
  };
}

interface TaskTapEvent {
  currentTarget: {
    dataset: { kind: "milestone" | "issue"; taskKey: string; projectId: string };
  };
}

const filterKeys: TaskFilter[] = ["todo", "upcoming", "overdue", "completed"];
const filterLabels: Record<TaskFilter, string> = {
  todo: "待办",
  upcoming: "近期",
  overdue: "逾期",
  completed: "已完成",
};

const presentFilters = (projects: MyTaskProject[]) => filterKeys.map((key) => {
  const count = projects.reduce(
    (total, project) => total + project.tasks.filter((task) => task.risk === key).length,
    0,
  );
  return { key, label: `${filterLabels[key]} ${count}` };
});

const presentProjects = (
  projects: MyTaskProject[],
  selectedFilter: TaskFilter,
): ProjectTaskView[] => projects
  .map((project) => ({
    ...project,
    visibleTasks: project.tasks.filter((task) => task.risk === selectedFilter),
  }))
  .map((project) => ({
    ...project,
    entryLabel: project.visibleTasks.length > 0
      && project.visibleTasks.every((task) => task.kind === "issue")
      ? "查看问题"
      : "进入看板",
    focusIssueId: project.visibleTasks.length > 0
      && project.visibleTasks.every((task) => task.kind === "issue")
      ? project.visibleTasks[0].task_key.replace("issue:", "")
      : "",
  }))
  .filter((project) => project.visibleTasks.length > 0);

Page({
  data: {
    projects: [] as ProjectTaskView[],
    sourceProjects: [] as MyTaskProject[],
    filters: presentFilters([]),
    selectedFilter: "todo" as TaskFilter,
    loading: true,
    loadError: false,
  },
  async onShow() {
    if (!wx.getStorageSync("access_token")) {
      wx.redirectTo({ url: "/pages/index/index" });
      return;
    }
    await this.loadTasks();
    void syncTabBarBadges();
  },
  async loadTasks() {
    this.setData({ loading: true, loadError: false });
    try {
      const sourceProjects = await api.myTasks();
      this.setData({
        sourceProjects,
        filters: presentFilters(sourceProjects),
        projects: presentProjects(sourceProjects, this.data.selectedFilter),
      });
    } catch {
      this.setData({ loadError: true });
    } finally {
      this.setData({ loading: false });
    }
  },
  selectFilter(event: FilterTapEvent) {
    const selectedFilter = event.currentTarget.dataset.key;
    this.setData({
      selectedFilter,
      projects: presentProjects(this.data.sourceProjects, selectedFilter),
    });
  },
  openProject(event: ProjectTapEvent) {
    const { id, code, name, focusIssueId } = event.currentTarget.dataset;
    wx.setStorageSync("current_project_id", id);
    wx.setStorageSync("current_project_code", code);
    wx.setStorageSync("current_project_name", name);
    if (focusIssueId) {
      wx.setStorageSync("focus_issue_id", focusIssueId);
      wx.switchTab({ url: "/pages/issues/issues" });
      return;
    }
    wx.navigateTo({ url: `/pages/dashboard/dashboard?projectId=${id}` });
  },
  openTask(event: TaskTapEvent) {
    const { kind, taskKey, projectId } = event.currentTarget.dataset;
    const project = this.data.sourceProjects.find((item) => item.project.id === projectId);
    if (!project) return;
    wx.setStorageSync("current_project_id", project.project.id);
    wx.setStorageSync("current_project_code", project.project.code);
    wx.setStorageSync("current_project_name", project.project.name);
    if (kind === "issue") {
      wx.setStorageSync("focus_issue_id", taskKey.replace("issue:", ""));
      wx.switchTab({ url: "/pages/issues/issues" });
      return;
    }
    wx.navigateTo({ url: `/pages/dashboard/dashboard?projectId=${project.project.id}` });
  },
});
