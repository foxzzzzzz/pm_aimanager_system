import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  listIssues: vi.fn().mockResolvedValue([]),
  listAuditLogs: vi.fn().mockResolvedValue([]),
  listIssueCreateProposals: vi.fn().mockResolvedValue([
    {
      id: "issue-proposal-1",
      project_id: "project-1",
      payload: { description: "待审批问题", owner_name: "成员10", accountable_names: ["成员02"], due_date: "2026-08-20" },
      status: "pending",
      created_at: "2026-08-12T10:30:00Z",
    },
  ]),
  approveIssueCreateProposal: vi.fn().mockResolvedValue({}),
  rejectIssueCreateProposal: vi.fn().mockResolvedValue({}),
  projectReview: vi.fn().mockResolvedValue({ members: [
    { name: "成员02", role: "经理", notes: null },
    { name: "成员10", role: "执行", notes: null },
  ] }),
  listMemberBindings: vi.fn().mockResolvedValue([
    {
      id: "binding-1",
      member_name: "成员08",
      status: "pending_review",
      provided_phone: "13900000008",
    },
  ]),
  approveMemberBinding: vi.fn().mockResolvedValue({}),
  createMemberInvitation: vi.fn().mockResolvedValue({
    invitation_token: "invite-token",
    mini_program_path: "pages/index/index?invitation=invite-token",
    url_link: "https://wxaurl.cn/invite",
    mini_program_code_data_url: "data:image/png;base64,aW52aXRl",
    entry_generation_error: null,
  }),
  createIssue: vi.fn().mockResolvedValue({}),
  updateIssue: vi.fn().mockResolvedValue({}),
  deleteIssue: vi.fn().mockResolvedValue({}),
  listChangeProposals: vi.fn().mockResolvedValue([
    {
      id: "proposal-1",
      milestone_code: "M23",
      kind: "delay",
      reason: "驱动联调延期",
      status: "pending",
      base_version_number: 1,
      created_at: "2026-08-12T10:30:00Z",
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
    expect(screen.getByText("2026-08-12 18:30")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /驳\s*回/ }));

    await waitFor(() =>
      expect(mocks.rejectChangeProposal).toHaveBeenCalledWith("proposal-1", "项目经理驳回"),
    );
  });

  it("lists and approves a pending issue creation", async () => {
    render(
      <IssuesAuditPage
        project={{ id: "project-1", code: "ZPD1322", name: "Lyra Pro", status: "active", current_version_number: 1 }}
      />,
    );
    fireEvent.click(await screen.findByRole("tab", { name: /问题新增审批/ }));
    expect(await screen.findByText("待审批问题")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "批准新增" }));
    await waitFor(() => expect(mocks.approveIssueCreateProposal).toHaveBeenCalledWith("issue-proposal-1"));
  });

  it("creates a member invitation from the binding tab", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    render(
      <IssuesAuditPage
        project={{ id: "project-1", code: "ZPD1322", name: "Lyra Pro", status: "active", current_version_number: 1 }}
      />,
    );
    fireEvent.click(await screen.findByRole("tab", { name: /成员绑定/ }));
    fireEvent.click(screen.getByRole("button", { name: "生成邀请" }));
    fireEvent.change(screen.getByLabelText("成员姓名"), { target: { value: "成员10" } });
    fireEvent.click(screen.getByRole("button", { name: "确认生成" }));

    await waitFor(() =>
      expect(mocks.createMemberInvitation).toHaveBeenCalledWith("project-1", {
        member_name: "成员10",
        expected_phone: undefined,
      }),
    );
    expect(await screen.findByDisplayValue("https://wxaurl.cn/invite")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "成员邀请小程序码" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "复制邀请入口" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("https://wxaurl.cn/invite"));
  });

  it("updates and deletes an issue from the admin table", async () => {
    mocks.listIssues.mockResolvedValue([
      {
        id: "issue-1",
        description: "原问题",
        impact: "原影响",
        owner_name: "成员10",
        accountable_names: ["成员02"],
        consulted_names: [],
        informed_names: [],
        risk: "upcoming",
        severity: "high",
        due_date: "2026-08-20",
        status: "待处理",
        revision: 1,
      },
    ]);
    render(
      <IssuesAuditPage
        project={{ id: "project-1", code: "ZPD1322", name: "Lyra Pro", status: "active", current_version_number: 1 }}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /编\s*辑/ }));
    expect(screen.getByLabelText("A 最终负责人")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("问题描述"), { target: { value: "修正后问题" } });
    fireEvent.click(screen.getByRole("button", { name: /保\s*存/ }));
    await waitFor(() => expect(mocks.updateIssue).toHaveBeenCalledWith(
      "issue-1",
      expect.objectContaining({ expected_revision: 1, description: "修正后问题" }),
    ));

    fireEvent.click(screen.getByRole("button", { name: /删\s*除/ }));
    fireEvent.change(screen.getByLabelText("删除原因"), { target: { value: "记录作废" } });
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
    await waitFor(() => expect(mocks.deleteIssue).toHaveBeenCalledWith("issue-1", 1, "记录作废"));
  });
});
