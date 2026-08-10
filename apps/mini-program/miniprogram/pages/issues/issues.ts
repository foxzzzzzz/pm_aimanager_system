import { api } from "../../services/api";
import { validateIssueCreate } from "../../services/form-validation.js";
import type { Issue } from "../../types";

interface InputEvent { detail: { value: string } }
interface PickerEvent { detail: { value: string } }
interface IssueTapEvent { currentTarget: { dataset: { id: string; revision: number } } }

Page({
  data: {
    projectId: "",
    projectCode: "",
    projectName: "",
    issues: [] as Issue[],
    description: "",
    impact: "",
    ownerName: "",
    dueDate: "",
    creating: false,
    actionIssueId: "",
  },
  async onShow() {
    const projectId = wx.getStorageSync<string>("current_project_id");
    this.setData({
      projectId,
      projectCode: wx.getStorageSync<string>("current_project_code"),
      projectName: wx.getStorageSync<string>("current_project_name"),
    });
    if (!projectId) return;
    try {
      this.setData({ issues: await api.issues(projectId) });
    } catch {
      wx.showToast({ title: "问题加载失败", icon: "none" });
    }
  },
  onDescription(event: InputEvent) { this.setData({ description: event.detail.value }); },
  onImpact(event: InputEvent) { this.setData({ impact: event.detail.value }); },
  onOwner(event: InputEvent) { this.setData({ ownerName: event.detail.value }); },
  onDueDate(event: PickerEvent) { this.setData({ dueDate: event.detail.value }); },
  selectProject() { wx.switchTab({ url: "/pages/projects/projects" }); },
  async createIssue() {
    if (this.data.creating) return;
    const validationError = validateIssueCreate(this.data);
    if (validationError) {
      wx.showToast({ title: validationError, icon: "none" });
      return;
    }
    this.setData({ creating: true });
    try {
      await api.createIssue(this.data.projectId, {
        description: this.data.description,
        impact: this.data.impact,
        owner_name: this.data.ownerName,
        severity: "high",
        due_date: this.data.dueDate,
      });
      this.setData({
        issues: await api.issues(this.data.projectId),
        description: "",
        impact: "",
        ownerName: "",
        dueDate: "",
      });
      wx.showToast({ title: "问题已登记", icon: "success" });
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
      this.setData({ issues: await api.issues(this.data.projectId) });
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
      this.setData({ issues: await api.issues(this.data.projectId) });
      wx.showToast({ title: "问题已作废", icon: "success" });
    } catch (error) {
      wx.showToast({ title: (error as Error).message, icon: "none" });
    } finally {
      this.setData({ actionIssueId: "" });
    }
  },
});
