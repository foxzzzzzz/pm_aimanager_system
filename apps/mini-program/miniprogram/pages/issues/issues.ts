import { api } from "../../services/api";
import { validateIssueCreate } from "../../services/form-validation.js";
import { formatDate, labelSeverity } from "../../services/presentation.js";
import type { Issue } from "../../types";

interface InputEvent { detail: { value: string } }
interface PickerEvent { detail: { value: string } }
interface MultiSelectEvent { detail: { value: string[] }; currentTarget: { dataset: { name: string } } }
interface IssueTapEvent { currentTarget: { dataset: { id: string; revision: number } } }

interface IssueView extends Issue {
  severityLabel: string;
  dueDateLabel: string;
  riskLabel: string;
}

const riskLabels = { todo: "待办", upcoming: "近期", overdue: "逾期", completed: "已完成" };

const presentIssues = (issues: Issue[]): IssueView[] => issues.map((issue) => ({
  ...issue,
  severityLabel: labelSeverity(issue.severity),
  dueDateLabel: formatDate(issue.due_date),
  riskLabel: riskLabels[issue.risk],
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
    projectMembers: [] as string[],
    accountableNames: [] as string[],
    consultedNames: [] as string[],
    informedNames: [] as string[],
    dueDate: "",
    severityOptions: ["low", "medium", "high", "critical"],
    severityLabels: ["低", "中", "高", "重大"],
    severityIndex: 2,
    statusOptions: ["待处理", "处理中", "待验证", "已解决"],
    statusIndex: 0,
    editingIssueId: "",
    editingRevision: 0,
    formVisible: false,
    creating: false,
    actionIssueId: "",
    loading: false,
    loadError: false,
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
      ...(projectChanged ? {
        formVisible: false,
        editingIssueId: "",
        editingRevision: 0,
        description: "",
        impact: "",
        dueDate: "",
        severityIndex: 2,
        statusIndex: 0,
      } : {}),
    });
    if (!projectId) {
      this.setData({ loading: false, loadError: false, issues: [] });
      return;
    }
    await this.loadIssues();
  },
  async loadIssues() {
    if (!this.data.projectId) return;
    this.setData({ loading: true, loadError: false });
    try {
      const [issues, review] = await Promise.all([
        api.issues(this.data.projectId),
        api.projectReview(this.data.projectId),
      ]);
      this.setData({
        issues: presentIssues(issues),
        projectMembers: review.members.map((member) => member.name),
        loadError: false,
      });
    } catch {
      this.setData({ loadError: true });
    } finally {
      this.setData({ loading: false });
    }
  },
  onDescription(event: InputEvent) { this.setData({ description: event.detail.value }); },
  onImpact(event: InputEvent) { this.setData({ impact: event.detail.value }); },
  onDueDate(event: PickerEvent) { this.setData({ dueDate: event.detail.value }); },
  onSeverity(event: PickerEvent) { this.setData({ severityIndex: Number(event.detail.value) }); },
  onStatus(event: PickerEvent) { this.setData({ statusIndex: Number(event.detail.value) }); },
  updateRaciMembers(event: MultiSelectEvent) {
    const field = event.currentTarget.dataset.name as "accountableNames" | "consultedNames" | "informedNames";
    this.setData({ [field]: event.detail.value });
  },
  selectProject() { wx.switchTab({ url: "/pages/projects/projects" }); },
  openCreateForm() {
    this.setData({
      formVisible: true,
      editingIssueId: "",
      editingRevision: 0,
      description: "",
      impact: "",
      ownerName: this.data.currentMemberName,
      accountableNames: [], consultedNames: [], informedNames: [],
      dueDate: "",
      severityIndex: 2,
      statusIndex: 0,
    });
    this.scrollToIssueForm();
  },
  editIssue(event: IssueTapEvent) {
    const issue = this.data.issues.find((item) => item.id === event.currentTarget.dataset.id);
    if (!issue) return;
    this.setData({
      formVisible: true,
      editingIssueId: issue.id,
      editingRevision: issue.revision,
      description: issue.description,
      impact: issue.impact,
      ownerName: issue.owner_name,
      accountableNames: issue.accountable_names,
      consultedNames: issue.consulted_names,
      informedNames: issue.informed_names,
      dueDate: issue.due_date,
      severityIndex: Math.max(0, this.data.severityOptions.indexOf(issue.severity)),
      statusIndex: Math.max(0, this.data.statusOptions.indexOf(issue.status)),
    });
    this.scrollToIssueForm();
  },
  cancelEdit() {
    this.setData({
      formVisible: false,
      editingIssueId: "",
      editingRevision: 0,
      description: "",
      impact: "",
      ownerName: this.data.currentMemberName,
      accountableNames: [], consultedNames: [], informedNames: [],
      dueDate: "",
      severityIndex: 2,
      statusIndex: 0,
    });
  },
  scrollToIssueForm() {
    wx.nextTick(() => {
      wx.pageScrollTo({ selector: "#issue-form", duration: 250 });
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
      let saved: Issue;
      if (isEditing) {
        saved = await api.updateIssue(this.data.editingIssueId, {
          expected_revision: this.data.editingRevision,
          description: this.data.description,
          impact: this.data.impact,
          severity: this.data.severityOptions[this.data.severityIndex],
          due_date: this.data.dueDate,
          status: this.data.statusOptions[this.data.statusIndex],
        });
      } else {
        saved = await api.createIssue(this.data.projectId, {
          description: this.data.description,
          impact: this.data.impact,
          owner_name: this.data.ownerName,
          accountable_names: this.data.accountableNames,
          consulted_names: this.data.consultedNames,
          informed_names: this.data.informedNames,
          severity: this.data.severityOptions[this.data.severityIndex],
          due_date: this.data.dueDate,
        });
      }
      const issues = this.data.issues.some((item) => item.id === saved.id)
        ? this.data.issues.map((item) => item.id === saved.id ? saved : item)
        : [saved, ...this.data.issues];
      this.cancelEdit();
      this.setData({ issues: presentIssues(issues) });
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
      const saved = await api.updateIssue(event.currentTarget.dataset.id, {
        expected_revision: event.currentTarget.dataset.revision,
        status: "处理中",
      });
      this.setData({
        issues: presentIssues(
          this.data.issues.map((item) => item.id === saved.id ? saved : item),
        ),
      });
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
      const saved = await api.deleteIssue(event.currentTarget.dataset.id, {
        expected_revision: event.currentTarget.dataset.revision,
        reason,
      });
      this.setData({
        issues: presentIssues(
          this.data.issues.map((item) => item.id === saved.id ? saved : item),
        ),
      });
      wx.showToast({ title: "问题已作废", icon: "success" });
    } catch (error) {
      wx.showToast({ title: (error as Error).message, icon: "none" });
    } finally {
      this.setData({ actionIssueId: "" });
    }
  },
});
