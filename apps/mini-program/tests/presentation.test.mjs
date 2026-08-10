import assert from "node:assert/strict";
import test from "node:test";

import {
  formatDate,
  formatDateTime,
  labelMessageType,
  labelPlanState,
  labelSeverity,
  presentPlan,
} from "../miniprogram/services/presentation.js";

test("presentation labels replace backend enum values", () => {
  assert.equal(labelPlanState("not_applicable"), "不适用");
  assert.equal(labelPlanState("tbd"), "待定");
  assert.equal(labelSeverity("critical"), "重大");
  assert.equal(labelMessageType("binding_approved"), "身份绑定");
  assert.equal(labelMessageType("unknown_event"), "系统消息");
});

test("presentation formats dates consistently for the configured timezone", () => {
  assert.equal(formatDate("2026-08-10"), "2026-08-10");
  assert.equal(formatDate(null), "—");
  assert.equal(formatDateTime("2026-08-10T07:35:27.450502+00:00", 480), "2026-08-10 15:35");
  assert.equal(formatDateTime("", 480), "—");
});

test("presentation renders scheduled, pending, and not-applicable plans", () => {
  assert.equal(
    presentPlan({ state: "scheduled", start_date: "2026-08-10", end_date: "2026-08-13" }),
    "2026-08-10 → 2026-08-13",
  );
  assert.equal(presentPlan({ state: "tbd", start_date: null, end_date: null }), "待定");
  assert.equal(presentPlan(null), "未设置");
});
