// Replace the base URL and disable development login before a real WeChat build.
export const runtimeConfig = {
  apiBaseUrl: "https://api.ereader.fun/api/v1",
  useDevelopmentLogin: false,
  developmentLoginCode: "",
  // Temporary fallback while the WeChat phone-number capability is unavailable.
  allowInvitationOnlyBinding: true,
  // Replace with the approved WeChat subscription-message template before release.
  subscriptionTemplateId: "SUkrUyXH_lnu4grmZ6OyyuahFu8oMfTqXSWKVmBQZQ0",
  // 节点结束日期距今天不超过该天数时，归入“近期”筛选。
  milestoneUpcomingDays: 14,
  // API 时间戳展示使用的业务时区偏移量，当前为 UTC+8。
  presentationTimezoneOffsetMinutes: 480,
  // 网络层在没有收到响应时自动重试的次数，重试复用同一个幂等键。
  requestRetryAttempts: 1,
  // 项目资料每次增量展示的记录数。
  projectReviewPageSize: 10,
  // 产品规格详情与备注超过该字符数时默认折叠，用户可按需展开。
  projectReviewCollapseLength: 90,
};
