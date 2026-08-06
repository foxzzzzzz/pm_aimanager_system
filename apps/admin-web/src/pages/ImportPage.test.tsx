import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({ api: { uploadImport: vi.fn(), publishImport: vi.fn() } }));

import ImportPage from "./ImportPage";

describe("ImportPage", () => {
  afterEach(cleanup);

  it("clears an analyzed record when the selected project changes", async () => {
    const first = { id: "one", code: "ONE", name: "One", status: "active", current_version_number: 1 };
    const second = { id: "two", code: "TWO", name: "Two", status: "active", current_version_number: 1 };
    const { rerender } = render(<ImportPage project={first} onPublished={vi.fn()} />);

    rerender(<ImportPage project={second} onPublished={vi.fn()} />);

    await waitFor(() => expect(screen.getByText("TWO")).toBeInTheDocument());
    expect(screen.queryByText("ONE")).not.toBeInTheDocument();
  });
});
