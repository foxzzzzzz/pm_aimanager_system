import { api } from "../../services/api";
import type { MyTask, MyTaskProject } from "../../types";

type TaskFilter = "todo" | "upcoming" | "overdue" | "completed";

interface ProjectTaskView extends MyTaskProject {
  visibleTasks: MyTask[];
}

interface FilterTapEvent {
  currentTarget: { dataset: { key: TaskFilter } };
}

interface ProjectTapEvent {
  currentTarget: { dataset: { id: string; code: string; name: string } };
}

const filterKeys: TaskFilter[] = ["todo", "upcoming", "overdue", "completed"];
const filterLabels: Record<TaskFilter, string> = {
  todo: "待办",
  upcoming: "近期",
  overdue: "逾期",
  completed: "已完成",
};

const presentProjects = (
  projects: MyTaskProject[],
  selectedFilter: TaskFilter,
): ProjectTaskView[] => projects
  .map((project) => ({
    ...project,
    visibleTasks: project.tasks.filter((task) => task.risk === selectedFilter),
  }))
  .filter((project) => project.visibleTasks.length > 0);

Page({
  data: {
    projects: [] as ProjectTaskView[],
    sourceProjects: [] as MyTaskProject[],
    filters: filterKeys.map((key) => ({ key, label: filterLabels[key] })),
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
  },
  async loadTasks() {
    this.setData({ loading: true, loadError: false });
    try {
      const sourceProjects = await api.myTasks();
      this.setData({
        sourceProjects,
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
    const { id, code, name } = event.currentTarget.dataset;
    wx.setStorageSync("current_project_id", id);
    wx.setStorageSync("current_project_code", code);
    wx.setStorageSync("current_project_name", name);
    wx.navigateTo({ url: `/pages/dashboard/dashboard?projectId=${id}` });
  },
});
