import assert from "node:assert/strict";
import test from "node:test";

import {
  filterProjectMembers,
  filterProductSpecs,
  filterRaciRows,
  hasLongSpecContent,
} from "../miniprogram/services/project-review-filter.js";

const specs = [
  {
    item: "CPU",
    major_category: "核心硬件",
    category: "芯片平台",
    configuration: "S565",
    core_information: "兼容 G300",
    selected_model: "S566 A17",
    notes: null,
  },
  {
    item: "外观",
    major_category: "工业设计",
    category: null,
    configuration: "高铝玻璃盖板",
    core_information: null,
    selected_model: null,
    notes: "5252 喷砂后壳",
  },
];

test("product specification search covers names, categories, details, models, and notes", () => {
  assert.deepEqual(filterProductSpecs(specs, "cpu"), [specs[0]]);
  assert.deepEqual(filterProductSpecs(specs, "芯片平台"), [specs[0]]);
  assert.deepEqual(filterProductSpecs(specs, "g300"), [specs[0]]);
  assert.deepEqual(filterProductSpecs(specs, "S566"), [specs[0]]);
  assert.deepEqual(filterProductSpecs(specs, "喷砂"), [specs[1]]);
});

test("product specification search trims keywords and restores all rows when cleared", () => {
  assert.deepEqual(filterProductSpecs(specs, "  高铝玻璃  "), [specs[1]]);
  assert.deepEqual(filterProductSpecs(specs, ""), specs);
  assert.deepEqual(filterProductSpecs(specs, "missing"), []);
});

test("member search covers names, roles, and notes", () => {
  const members = [
    { name: "成员甲", role: "项目经理", notes: "负责整体交付" },
    { name: "成员乙", role: "结构工程师", notes: null },
  ];

  assert.deepEqual(filterProjectMembers(members, "成员甲"), [members[0]]);
  assert.deepEqual(filterProjectMembers(members, "结构"), [members[1]]);
  assert.deepEqual(filterProjectMembers(members, "整体交付"), [members[0]]);
});

test("RACI search covers nodes, outputs, and assigned members", () => {
  const rows = [
    {
      code: "M06",
      name: "EVT投板",
      output: "设计文件",
      roles: [{ key: "R", names: "成员乙" }],
    },
    {
      code: "M10",
      name: "可靠性测试",
      output: "测试报告",
      roles: [{ key: "A", names: "成员甲" }],
    },
  ];

  assert.deepEqual(filterRaciRows(rows, "M06"), [rows[0]]);
  assert.deepEqual(filterRaciRows(rows, "测试报告"), [rows[1]]);
  assert.deepEqual(filterRaciRows(rows, "成员乙"), [rows[0]]);
});

test("long specification content is detected from details and notes", () => {
  assert.equal(hasLongSpecContent({ detail: "短内容", notes: null }, 10), false);
  assert.equal(hasLongSpecContent({ detail: "12345678", notes: "备注内容" }, 10), true);
});
