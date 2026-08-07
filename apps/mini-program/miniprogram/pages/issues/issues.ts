import { api } from "../../services/api";
import type { Issue } from "../../types";

interface InputEvent { detail: { value: string } }
interface PickerEvent { detail: { value: string } }
interface IssueTapEvent { currentTarget: { dataset: { id: string; revision: number } } }

Page({
  data: {
    projectId: "",
    issues: [] as Issue[],
    description: "",
    impact: "",
    ownerName: "",
    dueDate: "",
  },
  async onShow() {
    const projectId = wx.getStorageSync<string>("current_project_id");
    this.setData({ projectId });
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
  async createIssue() {
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
      });
      wx.showToast({ title: "问题已登记", icon: "success" });
    } catch {
      wx.showToast({ title: "请完整填写问题", icon: "none" });
    }
  },
  async startIssue(event: IssueTapEvent) {
    try {
      await api.updateIssue(event.currentTarget.dataset.id, {
        expected_revision: event.currentTarget.dataset.revision,
        status: "处理中",
      });
      this.setData({ issues: await api.issues(this.data.projectId) });
    } catch (reason) {
      wx.showToast({ title: (reason as Error).message, icon: "none" });
    }
  },
  async deleteIssue(event: IssueTapEvent) {
    const confirmation = await wx.showModal({
      title: "作废问题",
      content: "请输入作废原因",
      editable: true,
      placeholderText: "作废原因（必填）",
      confirmColor: "#c53030",
    });
    const reason = confirmation.content?.trim();
    if (!confirmation.confirm || !reason) return;
    try {
      await api.deleteIssue(event.currentTarget.dataset.id, {
        expected_revision: event.currentTarget.dataset.revision,
        reason,
      });
      this.setData({ issues: await api.issues(this.data.projectId) });
      wx.showToast({ title: "问题已作废", icon: "success" });
    } catch (error) {
      wx.showToast({ title: (error as Error).message, icon: "none" });
    }
  },
});
