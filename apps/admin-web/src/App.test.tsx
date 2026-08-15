import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

describe("App", () => {
  beforeEach(() => sessionStorage.setItem("admin_api_token", "test-token"));
  afterEach(() => {
    sessionStorage.clear();
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
    expect(screen.getByText("项目看板")).toBeInTheDocument();
    expect(screen.getByText("项目核对")).toBeInTheDocument();
    expect(screen.getByText("Excel导入")).toBeInTheDocument();
    expect(screen.getByText("版本历史")).toBeInTheDocument();
    expect(screen.getByText("问题与审计")).toBeInTheDocument();
    expect(screen.getByText("通知诊断")).toBeInTheDocument();
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
          business_date: "2026-08-12",
          active_plan_name: null,
          milestones: {},
          tasks: [],
          issues: [],
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

  it("confirms and deletes an empty project after a 204 response", async () => {
    const project = {
      id: "project-1",
      code: "TEST1",
      name: "TEST1",
      status: "active",
      current_version_number: 0,
    };
    const fetchMock = vi.fn((url: string, options?: RequestInit) => {
      if (url.endsWith("/projects") && !options?.method) {
        return Promise.resolve({ ok: true, status: 200, json: async () => [project] });
      }
      if (url.endsWith("/projects/project-1") && options?.method === "DELETE") {
        return Promise.resolve({ ok: true, status: 204, json: async () => { throw new Error("must not parse 204"); } });
      }
      if (url.endsWith("/projects/project-1/dashboard")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            project,
            current_version_number: 0,
            active_plan_name: null,
            business_date: "2026-08-15",
            milestones: {},
            tasks: [],
            issues: [],
            counts: { members: 0, milestones: 0, product_specs: 0, issues_open: 0 },
          }),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "删除项目" }));
    const dialog = await screen.findByRole("dialog", { name: "删除空项目" });
    expect(dialog).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: /删\s*除/ }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/projects/project-1"),
      expect.objectContaining({ method: "DELETE" }),
    ));
    await waitFor(() => expect(screen.queryByRole("button", { name: "删除项目" })).not.toBeInTheDocument());
  });
});
