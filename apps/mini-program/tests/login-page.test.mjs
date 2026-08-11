import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  invitationErrorMessage,
  projectAccessState,
} from "../miniprogram/services/login-page.js";

test("project access state exposes the projects entry for bound users", () => {
  assert.deepEqual(projectAccessState([{ id: "project-1" }]), {
    hasProjects: true,
    projectCount: 1,
  });
  assert.deepEqual(projectAccessState([]), {
    hasProjects: false,
    projectCount: 0,
  });
});

test("invalid invitation errors use an actionable localized message", () => {
  const expected = "邀请码已使用、已过期或已重新生成";

  assert.equal(invitationErrorMessage(new Error("Invitation not found")), expected);
  assert.equal(invitationErrorMessage(new Error("Request failed: 404")), expected);
  assert.equal(invitationErrorMessage(new Error("手机号不匹配")), "手机号不匹配");
  assert.equal(invitationErrorMessage("unknown"), "操作失败");
});

test("login page checks bound projects and exposes their entry", async () => {
  const source = await readFile(
    new URL("../miniprogram/pages/index/index.ts", import.meta.url),
    "utf8",
  );
  const template = await readFile(
    new URL("../miniprogram/pages/index/index.wxml", import.meta.url),
    "utf8",
  );

  assert.match(source, /refreshProjectAccess/);
  assert.match(source, /await api\.projects\(\)/);
  assert.match(source, /wx\.switchTab\(\{ url: "\/pages\/projects\/projects" \}\)/);
  assert.match(template, /进入我的项目/);
  assert.match(template, /!hasProjects \|\| invitationToken/);
});
