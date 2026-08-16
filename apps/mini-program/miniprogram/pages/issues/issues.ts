import { api } from "../../services/api";
import { validateIssueCreate } from "../../services/form-validation.js";
import { runtimeConfig } from "../../config";
import { formatDate, formatDateTime, labelSeverity } from "../../services/presentation.js";
import type { Issue, ProjectSummary } from "../../types";
import { syncTabBarBadges } from "../../services/tab-badges";

interface InputEvent { detail: { value: string } }
interface PickerEvent { detail: { value: string } }
interface MultiSelectEvent { detail: { value: string[] }; currentTarget: { dataset: { name: string } } }
interface IssueTapEvent { currentTarget: { dataset: { id: string; revision: number } } }

interface IssueView extends Issue {
  severityLabel: string;
  dueDateLabel: string;
  riskLabel: string;
  createdAtLabel: string;
  accountableLabel: string;
  consultedLabel: string;
  informedLabel: string;
}

interface MemberOption { name: string; checked: boolean }

const memberOptions = (members: string[], selected: string[]): MemberOption[] =>
  members.map((name) => ({ name, checked: selected.includes(name) }));

const riskLabels = { todo: "待办", upcoming: "近期", overdue: "逾期", completed: "已完成" };

const presentIssues = (issues: Issue[]): IssueView[] => issues.map((issue) => ({
  ...issue,
  severityLabel: labelSeverity(issue.severity),
  dueDateLabel: formatDate(issue.due_date),
  riskLabel: riskLabels[issue.risk],
  createdAtLabel: formatDateTime(
    issue.created_at,
    runtimeConfig.presentationTimezoneOffsetMinutes,
  ),
  accountableLabel: issue.accountable_names.join("、"),
  consultedLabel: issue.consulted_names.join("、"),
  informedLabel: issue.informed_names.join("、"),
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
    accountableOptions: [] as MemberOption[],
    consultedOptions: [] as MemberOption[],
    informedOptions: [] as MemberOption[],
    dueDate: "",
    severityOptions: ["low", "medium", "high", "critical"],
    severityLabels: ["低", "中", "高", "重大"],
    severityIndex: 2,
    statusOptions: ["待处理", "处理中", "待验证", "已解决"],
    statusIndex: 0,
    editingIssueId: "",
    focusedIssueId: "",
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
    const focusedIssueId = wx.getStorageSync<string>("focus_issue_id");
    if (focusedIssueId && this.data.issues.some((issue) => issue.id === focusedIssueId)) {
      wx.removeStorageSync("focus_issue_id");
      this.setData({ focusedIssueId });
      setTimeout(() => {
        wx.pageScrollTo({ selector: `#issue-${focusedIssueId}`, duration: 250 });
      }, 80);
    }
    void syncTabBarBadges();
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
        accountableOptions: memberOptions(
          review.members.map((member) => member.name),
          this.data.accountableNames,
        ),
        consultedOptions: memberOptions(
          review.members.map((member) => member.name),
          this.data.consultedNames,
        ),
        informedOptions: memberOptions(
          review.members.map((member) => member.name),
          this.data.informedNames,
        ),
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
  onOwner(event: PickerEvent) {
    this.setData({ ownerName: this.data.projectMembers[Number(event.detail.value)] });
  },
  onDueDate(event: PickerEvent) { this.setData({ dueDate: event.detail.value }); },
  onSeverity(event: PickerEvent) { this.setData({ severityIndex: Number(event.detail.value) }); },
  onStatus(event: PickerEvent) { this.setData({ statusIndex: Number(event.detail.value) }); },
  updateRaciMembers(event: MultiSelectEvent) {
    const field = event.currentTarget.dataset.name as "accountableNames" | "consultedNames" | "informedNames";
    const optionsField = field.replace("Names", "Options") as
      "accountableOptions" | "consultedOptions" | "informedOptions";
    this.setData({
      [field]: event.detail.value,
      [optionsField]: memberOptions(this.data.projectMembers, event.detail.value),
    });
  },
  async selectProject() {
    let projects: ProjectSummary[];
    try {
      projects = await api.projects();
    } catch (error) {
      wx.showToast({ title: (error as Error).message, icon: "none" });
      return;
    }
    if (!projects.length) return;
    try {
      const { tapIndex } = await wx.showActionSheet({
        itemList: projects.map((project) => `${project.code} · ${project.name}`),
      });
      const project = projects[tapIndex];
      if (!project || project.id === this.data.projectId) return;
      const currentMemberName = wx.getStorageSync<string>("current_member_name");
      wx.setStorageSync("current_project_id", project.id);
      wx.setStorageSync("current_project_code", project.code);
      wx.setStorageSync("current_project_name", project.name);
      this.setData({
        projectId: project.id,
        projectCode: project.code,
        projectName: project.name,
        currentMemberName,
        issues: [],
        formVisible: false,
        editingIssueId: "",
        editingRevision: 0,
        description: "",
        impact: "",
        ownerName: currentMemberName,
        dueDate: "",
        severityIndex: 2,
        statusIndex: 0,
      });
      await this.loadIssues();
      void syncTabBarBadges();
    } catch {
      // The user dismissed the action sheet.
    }
  },
  openCreateForm() {
    this.setData({
      formVisible: true,
      editingIssueId: "",
      editingRevision: 0,
      description: "",
      impact: "",
      ownerName: this.data.currentMemberName,
      accountableNames: [], consultedNames: [], informedNames: [],
      accountableOptions: memberOptions(this.data.projectMembers, []),
      consultedOptions: memberOptions(this.data.projectMembers, []),
      informedOptions: memberOptions(this.data.projectMembers, []),
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
      accountableOptions: memberOptions(this.data.projectMembers, issue.accountable_names),
      consultedOptions: memberOptions(this.data.projectMembers, issue.consulted_names),
      informedOptions: memberOptions(this.data.projectMembers, issue.informed_names),
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
          owner_name: this.data.ownerName,
          accountable_names: this.data.accountableNames,
          consulted_names: this.data.consultedNames,
          informed_names: this.data.informedNames,
          severity: this.data.severityOptions[this.data.severityIndex],
          due_date: this.data.dueDate,
          status: this.data.statusOptions[this.data.statusIndex],
        });
      } else {
        await api.createIssue(this.data.projectId, {
          description: this.data.description,
          impact: this.data.impact,
          owner_name: this.data.ownerName,
          accountable_names: this.data.accountableNames,
          consulted_names: this.data.consultedNames,
          informed_names: this.data.informedNames,
          severity: this.data.severityOptions[this.data.severityIndex],
          due_date: this.data.dueDate,
        });
        this.cancelEdit();
        wx.showToast({ title: "问题新增申请已提交", icon: "success" });
        return;
      }
      const issues = this.data.issues.map((item) => item.id === saved.id ? saved : item);
      this.cancelEdit();
      this.setData({ issues: presentIssues(issues) });
      wx.showToast({ title: "问题已更新", icon: "success" });
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
      placeholderText: "",
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
      wx.showToast({ title: "删除申请已提交", icon: "success" });
    } catch (error) {
      wx.showToast({ title: (error as Error).message, icon: "none" });
    } finally {
      this.setData({ actionIssueId: "" });
    }
  },
});
