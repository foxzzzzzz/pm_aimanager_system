Page({
  onLoad(options: Record<string, string | undefined>) {
    const projectId = options.projectId;
    const projectCode = options.projectCode;
    const projectName = options.projectName;
    const objectType = options.objectType;
    const objectId = options.objectId;
    if (!projectId) {
      wx.reLaunch({ url: "/pages/messages/messages" });
      return;
    }
    if (projectCode) wx.setStorageSync("current_project_code", projectCode);
    if (projectName) wx.setStorageSync("current_project_name", projectName);
    wx.setStorageSync("current_project_id", projectId);
    if (objectType === "issue" && objectId) {
      wx.setStorageSync("focus_issue_id", objectId);
      wx.switchTab({ url: "/pages/issues/issues" });
      return;
    }
    const query = objectType === "milestone" && objectId
      ? `&focusMilestoneCode=${encodeURIComponent(objectId)}`
      : "";
    wx.redirectTo({ url: `/pages/dashboard/dashboard?projectId=${projectId}${query}` });
  },
});
