import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readJson = async (relativePath) =>
  JSON.parse(await readFile(new URL(relativePath, import.meta.url), "utf8"));

test("mini program declares TypeScript and required pages", async () => {
  const projectConfig = await readJson("../project.config.json");
  const appConfig = await readJson("../miniprogram/app.json");

  assert.equal(projectConfig.compileType, "miniprogram");
  assert.equal(projectConfig.setting.useCompilerPlugins, false);
  assert.deepEqual(appConfig.pages, [
    "pages/index/index",
    "pages/projects/projects",
    "pages/dashboard/dashboard",
    "pages/milestone-update/milestone-update",
    "pages/issues/issues",
    "pages/messages/messages",
  ]);
  assert.deepEqual(appConfig.tabBar.list.map((item) => item.pagePath), [
    "pages/projects/projects",
    "pages/issues/issues",
    "pages/messages/messages",
  ]);
});

test("mini program provides authenticated API and structured update flows", async () => {
  const apiSource = await readFile(
    new URL("../miniprogram/services/api.ts", import.meta.url),
    "utf8",
  );
  const requestSource = await readFile(
    new URL("../miniprogram/services/request-core.mjs", import.meta.url),
    "utf8",
  );
  const updateSource = await readFile(
    new URL("../miniprogram/pages/milestone-update/milestone-update.ts", import.meta.url),
    "utf8",
  );
  const messagesSource = await readFile(
    new URL("../miniprogram/pages/messages/messages.ts", import.meta.url),
    "utf8",
  );

  assert.match(requestSource, /Authorization/);
  assert.match(apiSource, /mobile\/auth\/wechat/);
  assert.match(apiSource, /mobile\/messages/);
  assert.match(apiSource, /change-proposals/);
  assert.match(apiSource, /messages\/\$\{messageId\}\/read/);
  assert.match(updateSource, /completed/);
  assert.match(updateSource, /delay/);
  assert.match(updateSource, /requires_confirmation/);
  assert.match(apiSource, /mobile\/subscription-grants/);
  assert.match(messagesSource, /requestSubscribeMessage/);
});
