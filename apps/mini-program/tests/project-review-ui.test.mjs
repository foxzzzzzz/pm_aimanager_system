import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readSource = (relativePath) => readFile(new URL(relativePath, import.meta.url), "utf8");

test("project review provides member and RACI keyword search", async () => {
  const [source, template] = await Promise.all([
    readSource("../miniprogram/pages/project-review/project-review.ts"),
    readSource("../miniprogram/pages/project-review/project-review.wxml"),
  ]);

  assert.match(source, /onMemberKeywordInput/);
  assert.match(source, /onRaciKeywordInput/);
  assert.match(template, /placeholder="搜索姓名、角色或备注"/);
  assert.match(template, /placeholder="搜索节点、输出或成员"/);
  assert.match(template, /filteredMembers\.length/);
  assert.match(template, /filteredRaciRows\.length/);
});

test("long product specification content can be expanded and collapsed", async () => {
  const [source, template] = await Promise.all([
    readSource("../miniprogram/pages/project-review/project-review.ts"),
    readSource("../miniprogram/pages/project-review/project-review.wxml"),
  ]);

  assert.match(source, /toggleSpecDetail/);
  assert.match(template, /class="detail-toggle"/);
  assert.match(template, /展开详情/);
  assert.match(template, /收起详情/);
});
