// Replace the base URL and disable development login before a real WeChat build.
export const runtimeConfig = {
  apiBaseUrl: "http://192.168.11.127:18000/api/v1",
  useDevelopmentLogin: true,
  developmentLoginCode: "dev:mini-program-user",
  // Replace with the approved WeChat subscription-message template before release.
  subscriptionTemplateId: "replace-with-template-id",
  // 节点结束日期距今天不超过该天数时，归入“近期”筛选。
  milestoneUpcomingDays: 3,
};
