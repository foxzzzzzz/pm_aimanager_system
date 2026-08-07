import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import ProjectReviewPage from "./ProjectReviewPage";

vi.mock("../api", () => ({
  api: {
    projectReview: vi.fn(),
    projectEditableData: vi.fn(),
    createProjectChangeSet: vi.fn(),
    publishProjectChangeSet: vi.fn(),
    cancelProjectChangeSet: vi.fn(),
  },
}));

const project = {
  id: "project-1",
  code: "ZPD1322",
  name: "Lyra Pro",
  status: "active",
  current_version_number: 3,
};

describe("ProjectReviewPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows product specs, merged roles, RACI and filters TBD milestones", async () => {
    vi.mocked(api.projectReview).mockResolvedValue({
      current_version_number: 3,
      document_version: "V1.3",
      active_plan_name: "变更计划2（两次试产）",
      tbd_count: 1,
      product_specs: [
        {
          row_number: 10,
          major_category: "系统",
          category: "软件",
          item: "OS 版本",
          configuration: "Android 16",
          core_information: null,
          selected_model: null,
          notes: null,
          check_confirmation: null,
          check_content: null,
        },
      ],
      members: [
        { name: "测试成员", role: "结构经理 / 结构设计执行", notes: null },
      ],
      milestones: [
        {
          code: "M13",
          name: "DVT-SMT贴片",
          output: "样机",
          schedule: { state: "tbd", start_date: null, end_date: null },
          assignments: { R: ["测试成员"], A: ["项目经理"], C: [], I: [] },
          risk_note: null,
        },
        {
          code: "M01",
          name: "正式立项",
          output: null,
          schedule: { state: "scheduled", start_date: "2026-07-30", end_date: "2026-07-30" },
          assignments: { R: ["项目经理"], A: ["项目经理"], C: [], I: [] },
          risk_note: null,
        },
      ],
    });

    render(<ProjectReviewPage project={project} />);

    expect(await screen.findByText("Android 16")).toBeInTheDocument();
    fireEvent.click(screen.getByText("团队成员 1"));
    expect(await screen.findByText("结构经理 / 结构设计执行")).toBeInTheDocument();
    fireEvent.click(screen.getByText("里程碑与RACI 2"));
    expect(await screen.findByText("待确认节点 1 个")).toBeInTheDocument();
    expect(screen.getAllByText("测试成员").length).toBeGreaterThan(0);
    expect(screen.getAllByText("项目经理").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("checkbox", { name: "仅显示待确认节点" }));
    expect(screen.queryByText("正式立项")).not.toBeInTheDocument();
    expect(screen.getByText("DVT-SMT贴片")).toBeInTheDocument();
  });

  it("changes the product specification page size", async () => {
    vi.mocked(api.projectReview).mockResolvedValue({
      current_version_number: 3,
      document_version: "V1.3",
      active_plan_name: null,
      tbd_count: 0,
      product_specs: Array.from({ length: 70 }, (_, index) => ({
        row_number: index + 1,
        major_category: null,
        category: "分类",
        item: `规格项 ${index + 1}`,
        configuration: null,
        core_information: null,
        selected_model: null,
        notes: null,
        check_confirmation: null,
        check_content: null,
      })),
      members: [],
      milestones: [],
    });

    const { container } = render(<ProjectReviewPage project={project} />);

    expect(await screen.findByText("规格项 10")).toBeInTheDocument();
    expect(screen.queryByText("规格项 11")).not.toBeInTheDocument();

    fireEvent.mouseDown(container.querySelector(".ant-pagination-options .ant-select-selector")!);
    fireEvent.click(await screen.findByText("20 / page"));

    expect(await screen.findByText("规格项 20")).toBeInTheDocument();
    expect(screen.queryByText("规格项 21")).not.toBeInTheDocument();
  });

  it("previews and publishes a product specification correction", async () => {
    const productSpec = {
      row_number: 10,
      major_category: "系统",
      category: "软件",
      item: "OS 版本",
      configuration: "Android 16",
      core_information: null,
      selected_model: null,
      notes: null,
      check_confirmation: null,
      check_content: null,
    };
    vi.mocked(api.projectReview).mockResolvedValue({
      current_version_number: 3,
      document_version: "V1.3",
      active_plan_name: "变更计划2",
      tbd_count: 0,
      product_specs: [productSpec],
      members: [],
      milestones: [],
    });
    vi.mocked(api.projectEditableData).mockResolvedValue({
      current_version_number: 3,
      template_id: "lyra_project_spec",
      template_version: "1.0",
      document_version: "V1.3",
      source_sha256: "source",
      project: { code: "ZPD1322", name: "Lyra Pro" },
      active_plan_name: "变更计划2",
      product_specs: [productSpec],
      members: [],
      milestones: [],
      plan_versions: [],
    });
    vi.mocked(api.createProjectChangeSet).mockResolvedValue({
      id: "change-set-1",
      project_id: project.id,
      base_version_number: 3,
      source: "admin_web",
      operations: [],
      diff: [
        {
          path: "product_specs[0].configuration",
          operation: "changed",
          before: "Android 16",
          after: "Android 17",
        },
      ],
      reason: "规格核对修正",
      status: "pending",
    });
    vi.mocked(api.publishProjectChangeSet).mockResolvedValue({
      id: "version-4",
      version_number: 4,
      template_id: "lyra_project_spec",
      template_version: "1.0",
      document_version: "V1.3",
      created_at: "2026-08-07T00:00:00Z",
    });

    render(<ProjectReviewPage project={project} />);

    fireEvent.click(await screen.findByRole("button", { name: "修正" }));
    fireEvent.change(await screen.findByLabelText("配置/参数"), {
      target: { value: "Android 17" },
    });
    fireEvent.change(screen.getByLabelText("变更原因"), {
      target: { value: "规格核对修正" },
    });
    fireEvent.click(screen.getByRole("button", { name: "生成差异预览" }));

    expect(await screen.findByText(/Android 17/)).toBeInTheDocument();
    await waitFor(() => expect(api.createProjectChangeSet).toHaveBeenCalledWith(project.id, {
      base_version_number: 3,
      reason: "规格核对修正",
      operations: [
        expect.objectContaining({
          op: "replace",
          resource: "product_spec",
          key: "10",
          value: expect.objectContaining({ configuration: "Android 17" }),
        }),
      ],
    }));

    fireEvent.click(screen.getByRole("button", { name: "确认发布" }));
    expect(api.publishProjectChangeSet).toHaveBeenCalledWith("change-set-1", 3);
  });

  it("removes a member and its RACI references in one change set", async () => {
    vi.mocked(api.projectReview).mockResolvedValue({
      current_version_number: 3,
      document_version: "V1.3",
      active_plan_name: "变更计划2",
      tbd_count: 0,
      product_specs: [],
      members: [{ name: "测试成员", role: "结构经理", notes: null }],
      milestones: [{
        code: "M13",
        name: "DVT-SMT贴片",
        output: "样机",
        schedule: { state: "tbd", start_date: null, end_date: null },
        assignments: { R: ["测试成员"], A: ["项目经理"], C: [], I: [] },
        risk_note: null,
      }],
    });
    vi.mocked(api.projectEditableData).mockResolvedValue({
      current_version_number: 3,
      template_id: "lyra_project_spec",
      template_version: "1.0",
      document_version: "V1.3",
      source_sha256: "source",
      project: { code: "ZPD1322", name: "Lyra Pro" },
      active_plan_name: "变更计划2",
      product_specs: [],
      members: [{ name: "测试成员", role: "结构经理", phone: null, email: null, notes: null }],
      milestones: [{
        code: "M13",
        name: "DVT-SMT贴片",
        output: "样机",
        actual_completion: { state: "tbd", start_date: null, end_date: null },
        variance_days: null,
        variance_note: null,
        risk_note: null,
        assignments: { R: ["测试成员"], A: ["项目经理"], C: [], I: [] },
      }],
      plan_versions: [{
        name: "变更计划2",
        milestones: { "DVT-SMT贴片": { state: "tbd", start_date: null, end_date: null } },
      }],
    });
    vi.mocked(api.createProjectChangeSet).mockResolvedValue({
      id: "change-set-member",
      project_id: project.id,
      base_version_number: 3,
      source: "admin_web",
      operations: [],
      diff: [],
      reason: "成员离开项目",
      status: "pending",
    });

    render(<ProjectReviewPage project={project} />);

    fireEvent.click(await screen.findByText("团队成员 1"));
    const memberRow = screen.getByRole("row", { name: /测试成员/ });
    fireEvent.click(within(memberRow).getByRole("button", { name: /删\s*除/ }));
    fireEvent.change(await screen.findByLabelText("变更原因"), {
      target: { value: "成员离开项目" },
    });
    fireEvent.click(screen.getByRole("button", { name: "生成差异预览" }));

    await waitFor(() => expect(api.createProjectChangeSet).toHaveBeenCalledWith(project.id, {
      base_version_number: 3,
      reason: "成员离开项目",
      operations: [
        { op: "remove", resource: "member", key: "测试成员" },
        {
          op: "replace",
          resource: "raci",
          key: "M13",
          value: { R: [], A: ["项目经理"], C: [], I: [] },
        },
      ],
    }));
  });
});
