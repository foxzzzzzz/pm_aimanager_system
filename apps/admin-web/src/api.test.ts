import { afterEach, describe, expect, it, vi } from "vitest";

import { api, clearAdminToken, setAdminToken } from "./api";

describe("administrator API authentication", () => {
  afterEach(() => {
    clearAdminToken();
    vi.unstubAllGlobals();
  });

  it("uses a runtime bearer token and never sends a caller supplied actor id", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
    vi.stubGlobal("fetch", fetchMock);
    setAdminToken("runtime-secret");

    await api.listProjects();

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(options.headers).toMatchObject({ Authorization: "Bearer runtime-secret" });
    expect(options.headers).not.toHaveProperty("X-Actor-Id");
  });
});
