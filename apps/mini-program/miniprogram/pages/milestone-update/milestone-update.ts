import { api } from "../../services/api";
import { validateMilestoneUpdate } from "../../services/form-validation.js";
import { mergeMilestonePrefill } from "../../services/milestone-prefill.js";

interface InputEvent { detail: { value: string } }
interface PickerEvent { detail: { value: string } }

Page({
  data: {
    projectId: "",
    code: "",
    version: 0,
    kind: "completed" as "completed" | "delay",
    date: "",
    startDate: "",
    endDate: "",
    reason: "",
    naturalText: "",
    assistantVisible: false,
    prefillApplied: false,
    requiresConfirmation: false,
    prefillBusy: false,
    submitting: false,
  },
  onLoad(options: Record<string, string | undefined>) {
    this.setData({
      projectId: options.projectId || "",
      code: options.code || "",
      version: Number(options.version || 0),
    });
  },
  chooseCompleted() {
    this.setData({
      kind: "completed",
      requiresConfirmation: this.data.prefillApplied,
    });
  },
  chooseDelay() {
    this.setData({ kind: "delay", requiresConfirmation: this.data.prefillApplied });
  },
  onDate(event: PickerEvent) {
    this.setData({ date: event.detail.value, requiresConfirmation: this.data.prefillApplied });
  },
  onStartDate(event: PickerEvent) {
    this.setData({
      startDate: event.detail.value,
      requiresConfirmation: this.data.prefillApplied,
    });
  },
  onEndDate(event: PickerEvent) {
    this.setData({
      endDate: event.detail.value,
      requiresConfirmation: this.data.prefillApplied,
    });
  },
  onReason(event: InputEvent) {
    this.setData({ reason: event.detail.value, requiresConfirmation: this.data.prefillApplied });
  },
  onNaturalText(event: InputEvent) { this.setData({ naturalText: event.detail.value }); },
  toggleAssistant() {
    this.setData({ assistantVisible: !this.data.assistantVisible });
  },
  async prefill() {
    if (this.data.prefillBusy) return;
    if (!this.data.naturalText.trim()) {
      wx.showToast({ title: "请先输入更新描述", icon: "none" });
      return;
    }
    this.setData({ prefillBusy: true });
    try {
      const result = await api.prefill(this.data.naturalText);
      this.setData({
        ...mergeMilestonePrefill(this.data, result),
        assistantVisible: false,
      });
      wx.pageScrollTo({ selector: "#primary-form", duration: 250 });
    } catch (error) {
      wx.showToast({ title: (error as Error).message, icon: "none" });
    } finally {
      this.setData({ prefillBusy: false });
    }
  },
  confirmPrefill() {
    this.setData({ requiresConfirmation: false });
    wx.showToast({ title: "预填结果已确认", icon: "success" });
  },
  async submit() {
    if (this.data.submitting) return;
    const validationError = validateMilestoneUpdate(this.data);
    if (validationError) {
      wx.showToast({ title: validationError, icon: "none" });
      return;
    }
    this.setData({ submitting: true });
    try {
      await api.submitMilestone(this.data.projectId, this.data.code, {
        kind: this.data.kind,
        base_version_number: this.data.version,
        actual_completion_date: this.data.kind === "completed" ? this.data.date : null,
        start_date: this.data.kind === "delay" ? this.data.startDate : null,
        end_date: this.data.kind === "delay" ? this.data.endDate : null,
        reason: this.data.reason,
      });
      wx.showToast({ title: "已提交审批", icon: "success" });
      wx.navigateBack();
    } catch (error) {
      wx.showToast({ title: (error as Error).message, icon: "none" });
    } finally {
      this.setData({ submitting: false });
    }
  },
});
