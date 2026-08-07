import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import NotificationsPage from "./NotificationsPage";

describe("NotificationsPage", () => {
  beforeEach(() => sessionStorage.setItem("admin_api_token", "test-token"));
  afterEach(() => {
    cleanup();
    sessionStorage.clear();
    vi.unstubAllGlobals();
  });

  it("shows production readiness issues without hiding delivery diagnostics", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((input: string) =>
        Promise.resolve({
          ok: true,
          json: async () =>
            input.endsWith("/operations/status")
              ? {
                  status: "alert",
                  notification_failures: 2,
                  stale_pending: 1,
                  unbound_recipients: 0,
                  configuration_issues: ["a production WeChat AppID is required"],
                }
              : [],
        }),
      ),
    );

    render(<NotificationsPage />);

    expect(await screen.findByText("生产配置待完善")).toBeInTheDocument();
    expect(screen.getByText("a production WeChat AppID is required")).toBeInTheDocument();
    expect(screen.getByText("失败 2 条，滞留 1 条")).toBeInTheDocument();
    expect(screen.getByText("暂无通知投递记录")).toBeInTheDocument();
  });

  it("shows unbound recipients as an operational alert", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((input: string) =>
        Promise.resolve({
          ok: true,
          json: async () =>
            input.endsWith("/operations/status")
              ? {
                  status: "alert",
                  notification_failures: 0,
                  stale_pending: 0,
                  unbound_recipients: 2,
                  configuration_issues: [],
                }
              : [],
        }),
      ),
    );

    render(<NotificationsPage />);

    expect(await screen.findByText("通知运行异常")).toBeInTheDocument();
    expect(screen.getByText("未绑定接收人 2 人")).toBeInTheDocument();
  });
});
