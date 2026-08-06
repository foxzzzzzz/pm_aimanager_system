import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  listIssues: vi.fn().mockResolvedValue([]),
  listAuditLogs: vi.fn().mockResolvedValue([]),
  listMemberBindings: vi.fn().mockResolvedValue([
    {
      id: "binding-1",
      member_name: "成员08",
      status: "pending_review",
      provided_phone: "13900000008",
    },
  ]),
  approveMemberBinding: vi.fn().mockResolvedValue({}),
  listChangeProposals: vi.fn().mockResolvedValue([
    {
      id: "proposal-1",
      milestone_code: "M23",
      kind: "delay",
      reason: "驱动联调延期",
      status: "pending",
      base_version_number: 1,
    },
  ]),
  approveChangeProposal: vi.fn().mockResolvedValue({}),
  rejectChangeProposal: vi.fn().mockResolvedValue({}),
}));

vi.mock("../api", () => ({ api: mocks }));

import IssuesAuditPage from "./IssuesAuditPage";

describe("IssuesAuditPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("lists and approves pending member bindings", async () => {
    render(
      <IssuesAuditPage
        project={{
          id: "project-1",
          code: "ZPD1322",
          name: "Lyra Pro",
          status: "active",
          current_version_number: 1,
        }}
      />,
    );

    fireEvent.click(await screen.findByRole("tab", { name: /成员绑定/ }));
    expect(await screen.findByText("成员08")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /通\s*过/ }));

    await waitFor(() => expect(mocks.approveMemberBinding).toHaveBeenCalledWith("binding-1"));
  });

  it("lists and rejects a pending change proposal", async () => {
    render(
      <IssuesAuditPage
        project={{
          id: "project-1",
          code: "ZPD1322",
          name: "Lyra Pro",
          status: "active",
          current_version_number: 1,
        }}
      />,
    );

    fireEvent.click(await screen.findByRole("tab", { name: /变更审批/ }));
    expect(await screen.findByText("驱动联调延期")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /驳\s*回/ }));

    await waitFor(() =>
      expect(mocks.rejectChangeProposal).toHaveBeenCalledWith("proposal-1", "项目经理驳回"),
    );
  });
});
