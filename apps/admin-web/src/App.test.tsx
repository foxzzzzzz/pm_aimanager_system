import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("renders the Phase 0 shell", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "AI项目管理系统" })).toBeInTheDocument();
    expect(screen.getByText("工程基线已就绪")).toBeInTheDocument();
  });
});
