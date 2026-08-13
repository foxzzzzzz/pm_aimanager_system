import { syncTabBarBadges } from "./services/tab-badges";

App({
  globalData: {
    currentProjectId: "",
  },
  onShow() {
    void syncTabBarBadges();
  },
});
