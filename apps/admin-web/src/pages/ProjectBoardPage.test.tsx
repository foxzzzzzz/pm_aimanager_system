import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ dashboard: vi.fn() }));

mocks.dashboard.mockResolvedValue({
  project: { id: "project-1", code: "ZPD1322", name: "Lyra Pro" },
  current_version_number: 3,
  active_plan_name: "变更计划2",
  business_date: "2026-08-12",
  milestones: {},
  counts: { members: 19, milestones: 24, product_specs: 70, issues_open: 1 },
  tasks: [
    {
      code: "M01",
      name: "正式立项",
      plan: { state: "scheduled", start_date: "2026-08-01", end_date: "2026-08-11" },
      assignments: { R: ["成员10"], A: ["成员02"], C: [], I: [] },
      risk: "overdue",
    },
    {
      code: "M06",
      name: "EVT投板",
      plan: { state: "scheduled", start_date: "2026-08-15", end_date: "2026-08-15" },
      assignments: { R: ["成员08"], A: ["成员02"], C: ["成员03"], I: [] },
      risk: "upcoming",
    },
    {
      code: "M07",
      name: "模具T0",
      plan: { state: "not_applicable", start_date: null, end_date: null },
      assignments: { R: ["成员10"], A: ["成员02"], C: [], I: [] },
      risk: "todo",
    },
  ],
  issues: [
    {
      id: "issue-1",
      description: "Docker阻塞",
      impact: "影响验收",
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
  ],
});

vi.mock("../api", () => ({ api: mocks }));

import ProjectBoardPage from "./ProjectBoardPage";

describe("ProjectBoardPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it.each([
    ["legacy", ["M08", "M25", "M09"]],
    ["new", ["M08", "M09", "M10"]],
  ])("preserves business order for %s project software nodes", async (id, codes) => {
    mocks.dashboard.mockResolvedValueOnce({
      current_version_number: 1,
      business_date: "2026-10-22",
      tasks: codes.map((code, index) => ({
        code,
        name: ["EVT-SMT贴片", "驱动bring up", "EVT装机"][index],
        plan: { state: "scheduled", start_date: "2026-10-22", end_date: "2026-10-22" },
        assignments: { R: ["软件成员"], A: ["负责人"], C: [], I: [] },
        risk: "todo",
      })),
      issues: [],
    });
    render(<ProjectBoardPage project={{ id, code: id, name: id, status: "active", current_version_number: 1 }} />);
    await screen.findByText(`${codes[1]} · 驱动bring up`);
    const titles = screen.getAllByText(/M\d+ · /).map((element) => element.textContent);
    expect(titles).toEqual([
      `${codes[0]} · EVT-SMT贴片`, `${codes[1]} · 驱动bring up`, `${codes[2]} · EVT装机`,
    ]);
  });

  it("uses server risk groups and shows milestone RACI with issue summaries", async () => {
    const onNavigate = vi.fn();
    render(
      <ProjectBoardPage
        project={{
          id: "project-1",
          code: "ZPD1322",
          name: "Lyra Pro",
          status: "active",
          current_version_number: 3,
        }}
        onNavigate={onNavigate}
      />,
    );

    await screen.findByText("Docker阻塞");
    expect(screen.getByRole("tab", { name: "待办 0" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /逾期/ }));
    expect(screen.getByText("M01 · 正式立项")).toBeInTheDocument();
    expect(screen.getAllByText("R 成员10").length).toBeGreaterThan(0);
    expect(screen.getAllByText("A 成员02").length).toBeGreaterThan(0);
    expect(screen.getByText("Docker阻塞")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /近期/ }));
    expect(screen.getByText("M06 · EVT投板")).toBeInTheDocument();
    expect(screen.queryByText("M01 · 正式立项")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "管理问题" }));
    expect(onNavigate).toHaveBeenCalledWith("issues");
  });
});
