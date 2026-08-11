import assert from "node:assert/strict";
import test from "node:test";

import { filterProductSpecs } from "../miniprogram/services/project-review-filter.js";

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
