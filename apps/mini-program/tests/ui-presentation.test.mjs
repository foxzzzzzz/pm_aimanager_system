import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readSource = (relativePath) => readFile(new URL(relativePath, import.meta.url), "utf8");

test("dashboard uses consistent full-width action rows instead of default mini buttons", async () => {
  const template = await readSource(
    "../miniprogram/pages/dashboard/dashboard.wxml",
  );

  assert.match(template, /class="card-action summary-action"/);
  assert.match(template, /class="card-action milestone-action"/);
  assert.match(template, /查看项目资料/);
  assert.match(template, /更新进度/);
  assert.doesNotMatch(template, /size="mini" bindtap="openProjectReview"/);
  assert.doesNotMatch(template, /size="mini" data-code=.*bindtap="updateMilestone"/);
});

test("list pages avoid duplicate native navigation titles", async () => {
  const [projectsTemplate, reviewTemplate] = await Promise.all([
    readSource("../miniprogram/pages/projects/projects.wxml"),
    readSource("../miniprogram/pages/project-review/project-review.wxml"),
  ]);

  assert.doesNotMatch(projectsTemplate, /class="title">我的项目/);
  assert.doesNotMatch(reviewTemplate, /class="title">项目资料/);
});

test("global mobile layout uses compact cards and bottom safe-area spacing", async () => {
  const styles = await readSource("../miniprogram/app.wxss");

  assert.match(styles, /padding-bottom:\s*calc\([^)]*env\(safe-area-inset-bottom\)/);
  assert.match(styles, /\.card\s*\{[^}]*margin-bottom:\s*16rpx/s);
  assert.match(styles, /\.card\s*\{[^}]*padding:\s*24rpx/s);
});
