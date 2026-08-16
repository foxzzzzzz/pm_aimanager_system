import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  invitationErrorMessage,
  mobileSessionErrorMessage,
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

test("invalid mobile sessions require a fresh login", () => {
  assert.equal(
    mobileSessionErrorMessage(new Error("mobile session is invalid or expired")),
    "登录会话已失效，请重新登录后继续绑定",
  );
  assert.equal(mobileSessionErrorMessage(new Error("other failure")), null);
});

test("login page checks bound projects and exposes their entry", async () => {
  const [source, template, projectsSource, projectsTemplate] = await Promise.all([
    readFile(new URL("../miniprogram/pages/index/index.ts", import.meta.url), "utf8"),
    readFile(new URL("../miniprogram/pages/index/index.wxml", import.meta.url), "utf8"),
    readFile(new URL("../miniprogram/pages/projects/projects.ts", import.meta.url), "utf8"),
    readFile(new URL("../miniprogram/pages/projects/projects.wxml", import.meta.url), "utf8"),
  ]);

  assert.match(source, /refreshProjectAccess/);
  assert.match(source, /await api\.projects\(\)/);
  assert.match(source, /wx\.switchTab\(\{ url: "\/pages\/projects\/projects" \}\)/);
  assert.match(template, /进入我的项目/);
  assert.match(template, /!hasProjects \|\| invitationToken/);
  assert.match(projectsTemplate, /加入其他项目/);
  assert.match(projectsSource, /openJoinProject/);
  assert.match(projectsSource, /pages\/index\/index\?mode=join/);
});

test("logged-in users can open the invitation form to join another project", async () => {
  const [source, template] = await Promise.all([
    readFile(new URL("../miniprogram/pages/index/index.ts", import.meta.url), "utf8"),
    readFile(new URL("../miniprogram/pages/index/index.wxml", import.meta.url), "utf8"),
  ]);

  assert.match(source, /joinMode:\s*options\.mode === "join"/);
  assert.match(template, /!hasProjects \|\| invitationToken \|\| joinMode/);
});

test("login page keeps invitation-only binding behind its runtime switch", async () => {
  const source = await readFile(
    new URL("../miniprogram/pages/index/index.ts", import.meta.url),
    "utf8",
  );
  const template = await readFile(
    new URL("../miniprogram/pages/index/index.wxml", import.meta.url),
    "utf8",
  );

  assert.match(source, /bindWithInvitationOnly/);
  assert.match(source, /acceptInvitation\(undefined, undefined\)/);
  assert.match(source, /runtimeConfig\.allowInvitationOnlyBinding/);
  assert.match(template, /allowInvitationOnlyBinding/);
  assert.match(template, /使用邀请码直接绑定/);
  assert.match(template, /授权手机号并绑定/);
});
