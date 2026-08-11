import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readSource = (relativePath) => readFile(new URL(relativePath, import.meta.url), "utf8");

test("issues page keeps the creation form collapsed until requested", async () => {
  const [source, template] = await Promise.all([
    readSource("../miniprogram/pages/issues/issues.ts"),
    readSource("../miniprogram/pages/issues/issues.wxml"),
  ]);

  assert.match(source, /formVisible:\s*false/);
  assert.match(source, /openCreateForm\(\)/);
  assert.match(source, /formVisible:\s*true/);
  assert.match(template, /bindtap="openCreateForm"/);
  assert.match(template, /wx:if="\{\{formVisible\}\}"[^>]*id="issue-form"/);
});

test("issue editing opens the labeled form and cancellation returns to the list", async () => {
  const [source, template] = await Promise.all([
    readSource("../miniprogram/pages/issues/issues.ts"),
    readSource("../miniprogram/pages/issues/issues.wxml"),
  ]);

  assert.match(source, /editIssue[\s\S]*formVisible:\s*true/);
  assert.match(source, /cancelEdit[\s\S]*formVisible:\s*false/);
  assert.match(source, /pageScrollTo/);
  assert.match(template, /class="field-label">问题描述/);
  assert.match(template, /class="field-label">项目影响/);
  assert.match(template, /class="field-label">预计完成日期/);
  assert.match(template, /class="required">\*/);
});

test("issue cards use a consistent compact action group", async () => {
  const template = await readSource("../miniprogram/pages/issues/issues.wxml");

  assert.match(template, /class="issue-actions"/);
  assert.match(template, /class="issue-action edit-action"/);
  assert.match(template, /class="issue-action progress-action"/);
  assert.match(template, /class="issue-action danger-action"/);
});
