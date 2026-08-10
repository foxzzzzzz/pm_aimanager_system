// Replace the base URL and disable development login before a real WeChat build.
export const runtimeConfig = {
  apiBaseUrl: "http://192.168.11.127:18000/api/v1",
  useDevelopmentLogin: true,
  developmentLoginCode: "dev:mini-program-user",
  // Replace with the approved WeChat subscription-message template before release.
  subscriptionTemplateId: "replace-with-template-id",
  // 节点结束日期距今天不超过该天数时，归入“近期”筛选。
  milestoneUpcomingDays: 3,
  // API 时间戳展示使用的业务时区偏移量，当前为 UTC+8。
  presentationTimezoneOffsetMinutes: 480,
  // 网络层在没有收到响应时自动重试的次数，重试复用同一个幂等键。
  requestRetryAttempts: 1,
  // 项目资料每次增量展示的记录数。
  projectReviewPageSize: 10,
};
