import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  retrospectiveOptions: vi.fn(), listRetrospectives: vi.fn(), getRetrospective: vi.fn(),
  createRetrospective: vi.fn(), updateRetrospective: vi.fn(), confirmRetrospective: vi.fn(),
}));
vi.mock("../api", () => ({ api: mocks }));
import ProjectRetrospectivePage from "./ProjectRetrospectivePage";

const project = { id: "p1", code: "TEST", name: "测试项目", status: "active", current_version_number: 2 };
const report = {
  id: "r1", project_id: "p1", report_number: 1, revision: 2, status: "draft", created_at: "2026-10-26T01:00:00Z",
  created_by: "manager", confirmed_at: null, confirmed_by: null, supersedes_report_id: null,
  facts: {
    cutoff_at: "2026-10-26T01:00:00Z", date_basis: "calendar_days", project_version_number: 2, baseline: { version_number: 1, plan_name: "原计划" },
    milestones: [{ code: "M01", name: "研发完成", original_plan: { state: "scheduled", start_date: null, end_date: "2026-06-01" }, latest_plan: { state: "scheduled", start_date: null, end_date: "2026-06-15" }, variance_plan: { state: "scheduled", start_date: null, end_date: "2026-06-15" }, scope_change: null, actual_completion: { state: "scheduled", start_date: null, end_date: "2026-06-14" }, original_variance_days: 13, adjusted_variance_days: -1, effective_adjustment_count: 2, imported_plan_rows_count: 3, status: "completed", warnings: ["完成后计划变更"], assignments: { R: ["主R"], A: [], C: [], I: [] } }],
    timeline: [{ id: "event-1", source: "mobile", kind: "schedule", milestone_code: "M01", effective: true, occurred_at: null, recorded_at: "2026-10-26T01:00:00Z", status: "approved", before: "2026-06-01", after: "2026-06-15", reason: "原始申请理由", submitted_by: "主R", resolved_by: "项目经理", evidence_refs: ["proposal:p1"] }], warnings: ["导入前历史/未采集"],
  },
  review: { baseline_confirmed: false, baseline_note: "", reason_reviews: [], improvements: [] },
};

describe("ProjectRetrospectivePage", () => {
  beforeEach(() => {
    mocks.retrospectiveOptions.mockResolvedValue({ baselines: [{ version_number: 1, plan_name: "原计划" }], reason_categories: ["资源"] });
    mocks.listRetrospectives.mockResolvedValue([report]);
    mocks.getRetrospective.mockResolvedValue(report);
    mocks.createRetrospective.mockResolvedValue(report);
    mocks.updateRetrospective.mockResolvedValue(report);
    mocks.confirmRetrospective.mockResolvedValue({ ...report, status: "confirmed" });
  });
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it("shows an empty state without fetching when no project is selected", () => {
    render(<ProjectRetrospectivePage />);
    expect(screen.getByText("请先选择项目")).toBeInTheDocument();
    expect(mocks.listRetrospectives).not.toHaveBeenCalled();
  });

  it("renders frozen comparisons and evidence without replacing original reasons", async () => {
    render(<ProjectRetrospectivePage project={project} />);
    expect(await screen.findByText("+13 天")).toBeInTheDocument();
    expect(screen.getByText("-1 天")).toBeInTheDocument();
    expect(screen.getByText("原始申请理由")).toBeInTheDocument();
    expect(screen.getByText("导入前历史/未采集")).toBeInTheDocument();
    expect(screen.getByText("proposal:p1")).toBeInTheDocument();
    expect(screen.getByText(/小程序审批 · 计划调整/)).toBeInTheDocument();
  });

  it("saves baseline confirmation, manual reasons and improvements with the expected revision", async () => {
    render(<ProjectRetrospectivePage project={project} />);
    fireEvent.click(await screen.findByLabelText("已核对原始基准"));
    fireEvent.change(screen.getByLabelText("基准确认依据"), { target: { value: "已核对立项承诺" } });
    fireEvent.click(screen.getByRole("button", { name: "添加原因" }));
    fireEvent.change(screen.getByLabelText("确认原因 1"), { target: { value: "资源冲突" } });
    fireEvent.click(screen.getByRole("button", { name: "添加改进建议" }));
    fireEvent.change(screen.getByLabelText("具体动作 1"), { target: { value: "提前确认窗口" } });
    fireEvent.change(screen.getByLabelText("适用场景 1"), { target: { value: "资源排期" } });
    fireEvent.change(screen.getByLabelText("拟负责人 1"), { target: { value: "项目经理" } });
    fireEvent.change(screen.getByLabelText("验收思路 1"), { target: { value: "核对资源承诺" } });
    fireEvent.click(screen.getByRole("button", { name: "保存核对意见" }));
    await waitFor(() => expect(mocks.updateRetrospective).toHaveBeenCalledWith("r1", expect.objectContaining({
      expected_revision: 2, baseline_confirmed: true, baseline_note: "已核对立项承诺",
      reason_reviews: [expect.objectContaining({ confirmed_reason: "资源冲突", status: "pending" })],
      improvements: [expect.objectContaining({ action: "提前确认窗口" })],
    })));
  });

  it("keeps confirmed reports read only and creates a separate revision", async () => {
    mocks.listRetrospectives.mockResolvedValue([{ ...report, status: "confirmed" }]);
    mocks.getRetrospective.mockResolvedValue({ ...report, status: "confirmed" });
    render(<ProjectRetrospectivePage project={project} />);
    fireEvent.click(await screen.findByRole("button", { name: "创建修订草稿" }));
    await waitFor(() => expect(mocks.createRetrospective).toHaveBeenCalledWith("p1", expect.objectContaining({ supersedes_report_id: "r1" })));
    expect(mocks.updateRetrospective).not.toHaveBeenCalled();
  });

  it("preserves unsaved input and requires a new draft on a conflict", async () => {
    mocks.updateRetrospective.mockRejectedValue(Object.assign(new Error("快照已变化"), { status: 409 }));
    render(<ProjectRetrospectivePage project={project} />);
    fireEvent.change(await screen.findByLabelText("基准确认依据"), { target: { value: "保留人工输入" } });
    fireEvent.click(screen.getByRole("button", { name: "保存核对意见" }));
    expect(await screen.findByText(/请生成新草稿/)).toBeInTheDocument();
    expect(screen.getByLabelText("基准确认依据")).toHaveValue("保留人工输入");
    expect(mocks.createRetrospective).not.toHaveBeenCalled();
  });

  it("retains unsaved opinions in a new revision and requires baseline verification again", async () => {
    mocks.createRetrospective.mockResolvedValue({ ...report, id: "r2", report_number: 2, supersedes_report_id: "r1" });
    render(<ProjectRetrospectivePage project={project} />);
    fireEvent.change(await screen.findByLabelText("基准确认依据"), { target: { value: "尚未保存的意见" } });
    fireEvent.click(screen.getByLabelText("已核对原始基准"));
    fireEvent.click(screen.getByRole("button", { name: "生成新草稿并保留意见" }));
    await waitFor(() => expect(mocks.createRetrospective).toHaveBeenCalledWith("p1", { supersedes_report_id: "r1" }));
    expect(await screen.findByText(/上一份报告的人工意见已保留/)).toBeInTheDocument();
    expect(screen.getByLabelText("基准确认依据")).toHaveValue("尚未保存的意见");
    expect(screen.getByLabelText("已核对原始基准")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "确认报告" })).toBeDisabled();
  });

  it("requires saved baseline confirmation before confirming the frozen report", async () => {
    const verified = { ...report, review: { ...report.review, baseline_confirmed: true, baseline_note: "已核对" } };
    mocks.listRetrospectives.mockResolvedValue([verified]);
    render(<ProjectRetrospectivePage project={project} />);
    fireEvent.click(await screen.findByRole("button", { name: "确认报告" }));
    await waitFor(() => expect(mocks.confirmRetrospective).toHaveBeenCalledWith("r1", 2));
    await waitFor(() => expect(screen.queryByRole("button", { name: "保存核对意见" })).not.toBeInTheDocument());
  });

  it("does not display a previous project's delayed response", async () => {
    let resolve!: (value: typeof report[]) => void;
    mocks.listRetrospectives.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    const { rerender } = render(<ProjectRetrospectivePage project={project} />);
    rerender(<ProjectRetrospectivePage project={{ ...project, id: "p2" }} />);
    await screen.findByLabelText("基准确认依据");
    resolve([{ ...report, facts: { ...report.facts, warnings: ["旧项目数据不应显示"] } }]);
    await waitFor(() => expect(screen.queryByText("旧项目数据不应显示")).not.toBeInTheDocument());
  });

  it("requires a published project baseline before generating a report", async () => {
    mocks.retrospectiveOptions.mockResolvedValue({ baselines: [], reason_categories: [] });
    mocks.listRetrospectives.mockResolvedValue([]);
    render(<ProjectRetrospectivePage project={project} />);
    expect(await screen.findByText("请先发布项目，再生成复盘报告。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "生成新草稿" })).toBeDisabled();
    expect(mocks.createRetrospective).not.toHaveBeenCalled();
  });
});
