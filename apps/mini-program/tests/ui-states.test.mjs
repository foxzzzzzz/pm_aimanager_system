import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const readSource = (relativePath) => readFile(new URL(relativePath, import.meta.url), "utf8");

test("primary data pages expose persistent retry states", async () => {
  const pages = ["projects", "dashboard", "project-review", "issues", "messages"];

  for (const page of pages) {
    const [source, template] = await Promise.all([
      readSource(`../miniprogram/pages/${page}/${page}.ts`),
      readSource(`../miniprogram/pages/${page}/${page}.wxml`),
    ]);
    assert.match(source, /loadError/);
    assert.match(template, /加载失败/);
    assert.match(template, /重新加载/);
  }
});

test("message cards distinguish unread messages", async () => {
  const template = await readSource("../miniprogram/pages/messages/messages.wxml");

  assert.match(template, /class="unread-dot"/);
  assert.match(template, />未读</);
});

test("native tab bar provides normal and selected icons", async () => {
  const appConfig = JSON.parse(await readSource("../miniprogram/app.json"));

  for (const item of appConfig.tabBar.list) {
    assert.match(item.iconPath, /^assets\/tabbar\/.+\.png$/);
    assert.match(item.selectedIconPath, /^assets\/tabbar\/.+-active\.png$/);
    await access(new URL(`../miniprogram/${item.iconPath}`, import.meta.url));
    await access(new URL(`../miniprogram/${item.selectedIconPath}`, import.meta.url));
  }
});

test("native tab bar clearly distinguishes selected and unselected colors", async () => {
  const appConfig = JSON.parse(await readSource("../miniprogram/app.json"));

  assert.equal(appConfig.tabBar.color, "#9aa5a1");
  assert.equal(appConfig.tabBar.selectedColor, "#087a64");
});

test("upcoming milestone window is configured as fourteen days", async () => {
  const config = await readSource("../miniprogram/config.ts");

  assert.match(config, /milestoneUpcomingDays:\s*14/);
});
