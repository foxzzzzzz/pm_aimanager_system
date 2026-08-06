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
  assert.deepEqual(appConfig.pages, ["pages/index/index"]);
});
