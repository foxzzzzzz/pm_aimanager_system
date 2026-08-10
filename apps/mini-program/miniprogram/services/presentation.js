const planStateLabels = {
  scheduled: "已排期",
  tbd: "待定",
  not_applicable: "不适用",
};

const severityLabels = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "重大",
};

const messageTypeLabels = {
  binding_approved: "身份绑定",
  weekly_summary: "每周摘要",
  milestone_due_soon: "节点临期",
  milestone_due_today: "节点今日到期",
  milestone_overdue: "节点逾期",
  issue_due_soon: "问题临期",
  issue_due_today: "问题今日到期",
  issue_overdue: "问题逾期",
};

export const labelPlanState = (value) => planStateLabels[value] || "未知状态";

export const labelSeverity = (value) => severityLabels[value] || "未分级";

export const labelMessageType = (value) => messageTypeLabels[value] || "系统消息";

export const formatDate = (value) => value ? value.slice(0, 10) : "—";

export const formatDateTime = (value, timezoneOffsetMinutes) => {
  if (!value) return "—";
  const normalized = value.replace(/\.(\d{3})\d+/, ".$1");
  const timestamp = Date.parse(normalized);
  if (Number.isNaN(timestamp)) return value;
  const shifted = new Date(timestamp + timezoneOffsetMinutes * 60 * 1000);
  const year = shifted.getUTCFullYear();
  const month = String(shifted.getUTCMonth() + 1).padStart(2, "0");
  const day = String(shifted.getUTCDate()).padStart(2, "0");
  const hour = String(shifted.getUTCHours()).padStart(2, "0");
  const minute = String(shifted.getUTCMinutes()).padStart(2, "0");
  return `${year}-${month}-${day} ${hour}:${minute}`;
};

export const presentPlan = (plan) => {
  if (!plan) return "未设置";
  if (plan.state !== "scheduled") return labelPlanState(plan.state);
  return `${formatDate(plan.start_date)} → ${formatDate(plan.end_date)}`;
};
