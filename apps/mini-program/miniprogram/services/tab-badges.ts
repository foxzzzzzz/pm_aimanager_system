import { api } from "./api";

const updateBadge = (index: number, count: number) => {
  if (count > 0) {
    wx.setTabBarBadge({ index, text: String(Math.min(count, 99)) });
  } else {
    wx.removeTabBarBadge({ index });
  }
};

export async function syncTabBarBadges(): Promise<void> {
  if (!wx.getStorageSync("access_token")) return;
  try {
    const [projects, messages] = await Promise.all([api.projects(), api.messages()]);
    updateBadge(0, projects.reduce(
      (total, project) => total + project.pending_approval_count,
      0,
    ));
    updateBadge(2, messages.filter((message) => !message.is_read).length);
  } catch {
    // Page-level error states remain responsible for reporting request failures.
  }
}
