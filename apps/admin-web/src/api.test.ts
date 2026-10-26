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

  it("sends retrospective writes with independent idempotency keys and expected revisions", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    setAdminToken("runtime-secret");
    await api.retrospectiveOptions("p1");
    await api.listRetrospectives("p1");
    await api.getRetrospective("r1");
    await api.createRetrospective("p1", { baseline_version_number: 1, baseline_plan_name: "原计划" });
    await api.updateRetrospective("r1", { expected_revision: 2, baseline_confirmed: true, baseline_note: "已核对", reason_reviews: [], improvements: [] });
    await api.confirmRetrospective("r1", 3);
    expect(fetchMock.mock.calls.map(([url]) => url.split("/api/v1")[1])).toEqual([
      "/projects/p1/retrospective-options", "/projects/p1/retrospectives", "/retrospectives/r1",
      "/projects/p1/retrospectives", "/retrospectives/r1", "/retrospectives/r1/confirm",
    ]);
    const keys = fetchMock.mock.calls.slice(3).map(([, options]) => {
      expect(options.headers).toMatchObject({ Authorization: "Bearer runtime-secret", "Content-Type": "application/json" });
      return options.headers["X-Idempotency-Key"];
    });
    expect(new Set(keys).size).toBe(3);
    expect(fetchMock.mock.calls[4][1].method).toBe("PATCH");
    expect(JSON.parse(fetchMock.mock.calls[5][1].body)).toEqual({ expected_revision: 3 });
  });
});
