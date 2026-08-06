import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

describe("App", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders the Phase 3 project workspace", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
    );
    render(<App />);

    expect(screen.getByRole("heading", { name: "AI项目管理系统" })).toBeInTheDocument();
    expect(await screen.findByText("项目总览")).toBeInTheDocument();
    expect(screen.getByText("Excel导入")).toBeInTheDocument();
    expect(screen.getByText("版本历史")).toBeInTheDocument();
    expect(screen.getByText("问题与审计")).toBeInTheDocument();
  });

  it("creates a project through the management form", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: "project-1",
          code: "ZPD1322",
          name: "Lyra Pro",
          status: "active",
          current_version_number: 0,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          project: {
            id: "project-1",
            code: "ZPD1322",
            name: "Lyra Pro",
            status: "active",
            current_version_number: 0,
          },
          current_version_number: 0,
          active_plan_name: null,
          milestones: {},
          counts: { members: 0, milestones: 0, product_specs: 0, issues_open: 0 },
        }),
      });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "新建项目" }));
    fireEvent.change(screen.getByLabelText("项目编号"), { target: { value: "ZPD1322" } });
    fireEvent.change(screen.getByLabelText("项目名称"), { target: { value: "Lyra Pro" } });
    fireEvent.click(screen.getByRole("button", { name: /创\s*建/ }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(await screen.findByText("Lyra Pro")).toBeInTheDocument();
  });
});
