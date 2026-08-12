export function validateMilestoneUpdate({
  kind,
  date,
  startDate,
  endDate,
  reason,
  requiresConfirmation,
}) {
  if (requiresConfirmation) return "请先确认预填结果";
  if (kind === "completed" && !date) return "请选择实际完成日期";
  if (kind === "delay") {
    if (!startDate) return "请选择新开始日期";
    if (!endDate) return "请选择新完成日期";
    if (startDate > endDate) return "新完成日期不能早于新开始日期";
  }
  if (!reason.trim()) return "请填写更新原因";
  return null;
}

export function validateIssueCreate({ description, impact, ownerName, accountableNames, dueDate }) {
  if (!description.trim()) return "请填写问题描述";
  if (!impact.trim()) return "请填写项目影响";
  if (!ownerName.trim()) return "请填写责任人姓名";
  if (!accountableNames.length) return "请选择A最终负责人";
  if (!dueDate) return "请选择预计完成日期";
  return null;
}
