import assert from "node:assert/strict";
import test from "node:test";

import {
  buildMilestoneFilters,
  filterMilestones,
} from "../miniprogram/services/milestone-view.js";

const milestone = ({
  code,
  endDate = null,
  actualEndDate = null,
  planState = "scheduled",
}) => ({
  code,
  name: code,
  plan: planState === "missing"
    ? null
    : { state: planState, start_date: endDate, end_date: endDate },
  actual_completion: {
    state: actualEndDate ? "completed" : "not_started",
    start_date: actualEndDate,
    end_date: actualEndDate,
  },
  can_update: true,
  can_approve: false,
});

const milestones = [
  milestone({ code: "DONE", endDate: "2026-08-01", actualEndDate: "2026-08-01" }),
  milestone({ code: "LATE", endDate: "2026-08-09" }),
  milestone({ code: "TODAY", endDate: "2026-08-10" }),
  milestone({ code: "SOON", endDate: "2026-08-13" }),
  milestone({ code: "LATER", endDate: "2026-08-20" }),
  milestone({ code: "NA", planState: "not_applicable" }),
];

test("milestone filters expose stable counts at date boundaries", () => {
  assert.deepEqual(buildMilestoneFilters(milestones, "2026-08-10"), [
    { key: "todo", label: "待办", count: 4 },
    { key: "upcoming", label: "近期", count: 2 },
    { key: "overdue", label: "逾期", count: 1 },
    { key: "completed", label: "已完成", count: 1 },
    { key: "all", label: "全部", count: 6 },
  ]);
});

test("milestone filters exclude completed and not-applicable nodes from todo", () => {
  assert.deepEqual(
    filterMilestones(milestones, "todo", "2026-08-10").map((item) => item.code),
    ["LATE", "TODAY", "SOON", "LATER"],
  );
  assert.deepEqual(
    filterMilestones(milestones, "upcoming", "2026-08-10").map((item) => item.code),
    ["TODAY", "SOON"],
  );
  assert.deepEqual(
    filterMilestones(milestones, "overdue", "2026-08-10").map((item) => item.code),
    ["LATE"],
  );
  assert.deepEqual(
    filterMilestones(milestones, "completed", "2026-08-10").map((item) => item.code),
    ["DONE"],
  );
});

test("upcoming defaults to today through the next fourteen days", () => {
  const boundaryMilestones = [
    milestone({ code: "TODAY", endDate: "2026-08-10" }),
    milestone({ code: "DAY14", endDate: "2026-08-24" }),
    milestone({ code: "DAY15", endDate: "2026-08-25" }),
  ];

  assert.deepEqual(
    filterMilestones(boundaryMilestones, "upcoming", "2026-08-10", 14)
      .map((item) => item.code),
    ["TODAY", "DAY14"],
  );
});
