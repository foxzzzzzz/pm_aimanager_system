import { api } from "../../services/api";

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
    requiresConfirmation: false,
  },
  onLoad(options: Record<string, string | undefined>) {
    this.setData({
      projectId: options.projectId || "",
      code: options.code || "",
      version: Number(options.version || 0),
    });
  },
  chooseCompleted() { this.setData({ kind: "completed" }); },
  chooseDelay() { this.setData({ kind: "delay" }); },
  onDate(event: PickerEvent) { this.setData({ date: event.detail.value }); },
  onStartDate(event: PickerEvent) { this.setData({ startDate: event.detail.value }); },
  onEndDate(event: PickerEvent) { this.setData({ endDate: event.detail.value }); },
  onReason(event: InputEvent) { this.setData({ reason: event.detail.value }); },
  onNaturalText(event: InputEvent) { this.setData({ naturalText: event.detail.value }); },
  async prefill() {
    const result = await api.prefill(this.data.naturalText);
    this.setData({
      code: result.milestone_code || this.data.code,
      kind: result.kind || this.data.kind,
      startDate: result.end_date || this.data.startDate,
      endDate: result.end_date || this.data.endDate,
      reason: result.reason,
      requiresConfirmation: result.requires_confirmation,
    });
  },
  async submit() {
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
    } catch {
      wx.showToast({ title: "提交失败，请检查字段", icon: "none" });
    }
  },
});
