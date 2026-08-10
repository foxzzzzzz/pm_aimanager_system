import { api } from "../../services/api";
import { validateIssueCreate } from "../../services/form-validation.js";
import { formatDate, labelSeverity } from "../../services/presentation.js";
import type { Issue } from "../../types";

interface InputEvent { detail: { value: string } }
interface PickerEvent { detail: { value: string } }
interface IssueTapEvent { currentTarget: { dataset: { id: string; revision: number } } }

interface IssueView extends Issue {
  severityLabel: string;
  dueDateLabel: string;
}

const presentIssues = (issues: Issue[]): IssueView[] => issues.map((issue) => ({
  ...issue,
  severityLabel: labelSeverity(issue.severity),
  dueDateLabel: formatDate(issue.due_date),
}));

Page({
  data: {
    projectId: "",
    projectCode: "",
    projectName: "",
    currentMemberName: "",
    issues: [] as IssueView[],
    description: "",
    impact: "",
    ownerName: "",
    dueDate: "",
    severityOptions: ["low", "medium", "high", "critical"],
    severityLabels: ["低", "中", "高", "重大"],
    severityIndex: 2,
    statusOptions: ["待处理", "处理中", "待验证", "已解决"],
    statusIndex: 0,
    editingIssueId: "",
    editingRevision: 0,
    creating: false,
    actionIssueId: "",
    loading: false,
  },
  async onShow() {
    const projectId = wx.getStorageSync<string>("current_project_id");
    const currentMemberName = wx.getStorageSync<string>("current_member_name");
    const projectChanged = projectId !== this.data.projectId;
    this.setData({
      projectId,
      projectCode: wx.getStorageSync<string>("current_project_code"),
      projectName: wx.getStorageSync<string>("current_project_name"),
      currentMemberName,
      ownerName: projectChanged ? currentMemberName : this.data.ownerName || currentMemberName,
      issues: projectChanged ? [] : this.data.issues,
    });
    if (!projectId) {
      this.setData({ loading: false, issues: [] });
      return;
    }
    this.setData({ loading: true });
    try {
      this.setData({ issues: presentIssues(await api.issues(projectId)) });
    } catch {
      wx.showToast({ title: "问题加载失败", icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },
  onDescription(event: InputEvent) { this.setData({ description: event.detail.value }); },
  onImpact(event: InputEvent) { this.setData({ impact: event.detail.value }); },
  onOwner(event: InputEvent) { this.setData({ ownerName: event.detail.value }); },
  onDueDate(event: PickerEvent) { this.setData({ dueDate: event.detail.value }); },
  onSeverity(event: PickerEvent) { this.setData({ severityIndex: Number(event.detail.value) }); },
  onStatus(event: PickerEvent) { this.setData({ statusIndex: Number(event.detail.value) }); },
  selectProject() { wx.switchTab({ url: "/pages/projects/projects" }); },
  editIssue(event: IssueTapEvent) {
    const issue = this.data.issues.find((item) => item.id === event.currentTarget.dataset.id);
    if (!issue) return;
    this.setData({
      editingIssueId: issue.id,
      editingRevision: issue.revision,
      description: issue.description,
      impact: issue.impact,
      ownerName: issue.owner_name,
      dueDate: issue.due_date,
      severityIndex: Math.max(0, this.data.severityOptions.indexOf(issue.severity)),
      statusIndex: Math.max(0, this.data.statusOptions.indexOf(issue.status)),
    });
  },
  cancelEdit() {
    this.setData({
      editingIssueId: "",
      editingRevision: 0,
      description: "",
      impact: "",
      ownerName: this.data.currentMemberName,
      dueDate: "",
      severityIndex: 2,
      statusIndex: 0,
    });
  },
  async createIssue() {
    if (this.data.creating) return;
    const validationError = validateIssueCreate(this.data);
    if (validationError) {
      wx.showToast({ title: validationError, icon: "none" });
      return;
    }
    const isEditing = Boolean(this.data.editingIssueId);
    this.setData({ creating: true });
    try {
      if (isEditing) {
        await api.updateIssue(this.data.editingIssueId, {
          expected_revision: this.data.editingRevision,
          description: this.data.description,
          impact: this.data.impact,
          severity: this.data.severityOptions[this.data.severityIndex],
          due_date: this.data.dueDate,
          status: this.data.statusOptions[this.data.statusIndex],
        });
      } else {
        await api.createIssue(this.data.projectId, {
          description: this.data.description,
          impact: this.data.impact,
          owner_name: this.data.ownerName,
          severity: this.data.severityOptions[this.data.severityIndex],
          due_date: this.data.dueDate,
        });
      }
      this.cancelEdit();
      this.setData({ issues: presentIssues(await api.issues(this.data.projectId)) });
      wx.showToast({ title: isEditing ? "问题已更新" : "问题已登记", icon: "success" });
    } catch (error) {
      wx.showToast({ title: (error as Error).message, icon: "none" });
    } finally {
      this.setData({ creating: false });
    }
  },
  async startIssue(event: IssueTapEvent) {
    if (this.data.actionIssueId) return;
    this.setData({ actionIssueId: event.currentTarget.dataset.id });
    try {
      await api.updateIssue(event.currentTarget.dataset.id, {
        expected_revision: event.currentTarget.dataset.revision,
        status: "处理中",
      });
      this.setData({ issues: presentIssues(await api.issues(this.data.projectId)) });
    } catch (reason) {
      wx.showToast({ title: (reason as Error).message, icon: "none" });
    } finally {
      this.setData({ actionIssueId: "" });
    }
  },
  async deleteIssue(event: IssueTapEvent) {
    if (this.data.actionIssueId) return;
    const confirmation = await wx.showModal({
      title: "作废问题",
      content: "请输入作废原因",
      editable: true,
      placeholderText: "作废原因（必填）",
      confirmColor: "#c53030",
    });
    const reason = confirmation.content?.trim();
    if (!confirmation.confirm || !reason) return;
    this.setData({ actionIssueId: event.currentTarget.dataset.id });
    try {
      await api.deleteIssue(event.currentTarget.dataset.id, {
        expected_revision: event.currentTarget.dataset.revision,
        reason,
      });
      this.setData({ issues: presentIssues(await api.issues(this.data.projectId)) });
      wx.showToast({ title: "问题已作废", icon: "success" });
    } catch (error) {
      wx.showToast({ title: (error as Error).message, icon: "none" });
    } finally {
      this.setData({ actionIssueId: "" });
    }
  },
});
