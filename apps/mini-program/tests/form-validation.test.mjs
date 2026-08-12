import assert from "node:assert/strict";
import test from "node:test";

import {
  validateIssueCreate,
  validateMilestoneUpdate,
} from "../miniprogram/services/form-validation.js";

test("milestone update requires explicit confirmation after prefill", () => {
  assert.equal(
    validateMilestoneUpdate({
      kind: "completed",
      date: "2026-08-10",
      startDate: "",
      endDate: "",
      reason: "节点已完成",
      requiresConfirmation: true,
    }),
    "请先确认预填结果",
  );
});

test("milestone update validates completed and delay fields", () => {
  assert.equal(
    validateMilestoneUpdate({
      kind: "completed",
      date: "",
      startDate: "",
      endDate: "",
      reason: "节点已完成",
      requiresConfirmation: false,
    }),
    "请选择实际完成日期",
  );
  assert.equal(
    validateMilestoneUpdate({
      kind: "delay",
      date: "",
      startDate: "2026-08-20",
      endDate: "2026-08-19",
      reason: "联调延期",
      requiresConfirmation: false,
    }),
    "新完成日期不能早于新开始日期",
  );
  assert.equal(
    validateMilestoneUpdate({
      kind: "delay",
      date: "",
      startDate: "2026-08-19",
      endDate: "2026-08-20",
      reason: "联调延期",
      requiresConfirmation: false,
    }),
    null,
  );
});

test("issue creation validates every required field", () => {
  assert.equal(
    validateIssueCreate({
      description: "",
      impact: "影响试产",
      ownerName: "测试成员",
      accountableNames: [],
      dueDate: "2026-08-20",
    }),
    "请填写问题描述",
  );
  assert.equal(
    validateIssueCreate({
      description: "驱动异常",
      impact: "影响试产",
      ownerName: "测试成员",
      accountableNames: ["审批成员"],
      dueDate: "2026-08-20",
    }),
    null,
  );
  assert.equal(
    validateIssueCreate({
      description: "驱动异常",
      impact: "影响试产",
      ownerName: "测试成员",
      accountableNames: [],
      dueDate: "2026-08-20",
    }),
    "请选择A最终负责人",
  );
});
