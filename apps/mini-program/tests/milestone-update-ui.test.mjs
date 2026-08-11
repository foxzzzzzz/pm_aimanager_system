import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readSource = (relativePath) => readFile(new URL(relativePath, import.meta.url), "utf8");

test("milestone update keeps natural-language assistance collapsed by default", async () => {
  const [source, template] = await Promise.all([
    readSource("../miniprogram/pages/milestone-update/milestone-update.ts"),
    readSource("../miniprogram/pages/milestone-update/milestone-update.wxml"),
  ]);

  assert.match(source, /assistantVisible:\s*false/);
  assert.match(source, /toggleAssistant\(\)/);
  assert.match(template, /bindtap="toggleAssistant"/);
  assert.match(template, /wx:if="\{\{assistantVisible\}\}"/);
});

test("milestone update presents a labeled primary form and segmented update type", async () => {
  const template = await readSource(
    "../miniprogram/pages/milestone-update/milestone-update.wxml",
  );

  assert.match(template, /class="update-options"/);
  assert.match(template, /class="field-label">实际完成日期/);
  assert.match(template, /class="field-label">新开始日期/);
  assert.match(template, /class="field-label">更新原因/);
  assert.match(template, /class="required">\*/);
  assert.match(template, /确认并提交审批/);
});

test("prefill returns users to the primary form for confirmation", async () => {
  const source = await readSource(
    "../miniprogram/pages/milestone-update/milestone-update.ts",
  );

  assert.match(source, /prefill[\s\S]*assistantVisible:\s*false/);
  assert.match(source, /prefill[\s\S]*pageScrollTo/);
});
