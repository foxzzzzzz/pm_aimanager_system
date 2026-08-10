import assert from "node:assert/strict";
import test from "node:test";

import { mergeMilestonePrefill } from "../miniprogram/services/milestone-prefill.js";

test("milestone prefill preserves distinct start and end dates", () => {
  assert.deepEqual(
    mergeMilestonePrefill(
      { code: "M01", kind: "delay", startDate: "", endDate: "", reason: "" },
      {
        milestone_code: "M23",
        kind: "delay",
        start_date: "2026-08-20",
        end_date: "2026-08-30",
        reason: "驱动联调",
        requires_confirmation: true,
      },
    ),
    {
      code: "M23",
      kind: "delay",
      startDate: "2026-08-20",
      endDate: "2026-08-30",
      reason: "驱动联调",
      prefillApplied: true,
      requiresConfirmation: true,
    },
  );
});
