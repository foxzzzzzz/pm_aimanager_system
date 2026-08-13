import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readSource = (relativePath) => readFile(new URL(relativePath, import.meta.url), "utf8");

test("dashboard uses right-aligned primary mini actions consistent with approval", async () => {
  const [source, template, styles] = await Promise.all([
    readSource("../miniprogram/pages/dashboard/dashboard.ts"),
    readSource("../miniprogram/pages/dashboard/dashboard.wxml"),
    readSource("../miniprogram/pages/dashboard/dashboard.wxss"),
  ]);

  assert.match(template, /class="card-action summary-action"/);
  assert.match(template, /class="card-action milestone-action"/);
  assert.match(template, /查看项目资料/);
  assert.match(template, /更新进度/);
  assert.match(template, /class="card-action summary-action" size="mini" type="primary" bindtap="openProjectReview"/);
  assert.match(template, /class="card-action milestone-action" size="mini" type="primary" data-code=.*bindtap="updateMilestone"/);
  assert.doesNotMatch(template, /class="action-arrow"/);
  assert.match(styles, /\.card-action-row\s*\{[^}]*justify-content:\s*flex-end/s);
  assert.match(styles, /\.card-action\s*\{[^}]*margin:\s*0/s);
  assert.match(styles, /\.proposal-actions\s*\{[^}]*justify-content:\s*flex-end/s);
  assert.match(styles, /\.proposal-actions button\s*\{[^}]*margin:\s*0/s);
  assert.match(template, /class="tag approval-tag">\{\{.*待我审批.*\}\}/);
  assert.match(template, /本人提交 · 可审批/);
  assert.match(template, /提交时间：\{\{item\.createdAtLabel\}\}/);
  assert.match(template, /wx:if="\{\{item\.can_resolve\}\}" class="proposal-actions"/);
  assert.match(source, /formatDateTime\(\s*item\.created_at/s);
  assert.match(styles, /\.approval-tag\s*\{[^}]*color:\s*#b54708/s);
  assert.match(styles, /\.approval-tag\s*\{[^}]*background:\s*#fff1e6/s);
});

test("list pages avoid duplicate native navigation titles", async () => {
  const [projectsTemplate, reviewTemplate] = await Promise.all([
    readSource("../miniprogram/pages/projects/projects.wxml"),
    readSource("../miniprogram/pages/project-review/project-review.wxml"),
  ]);

  assert.doesNotMatch(projectsTemplate, /class="title">我的项目/);
  assert.doesNotMatch(reviewTemplate, /class="title">项目资料/);
});

test("issue RACI checkboxes rely on checkbox-group values without unsupported WXML calls", async () => {
  const [template, source] = await Promise.all([
    readSource("../miniprogram/pages/issues/issues.wxml"),
    readSource("../miniprogram/pages/issues/issues.ts"),
  ]);

  assert.match(template, /data-name="accountableNames" bindchange="updateRaciMembers"/);
  assert.match(template, /data-name="consultedNames" bindchange="updateRaciMembers"/);
  assert.match(template, /data-name="informedNames" bindchange="updateRaciMembers"/);
  assert.doesNotMatch(template, /checked="\{\{[^}]*\.indexOf\(/);
  assert.match(source, /\[field\]:\s*event\.detail\.value/);
  assert.match(source, /\[optionsField\]:\s*memberOptions/);
});

test("issue creation selects any project member as R and waits for approval", async () => {
  const [template, source, apiSource] = await Promise.all([
    readSource("../miniprogram/pages/issues/issues.wxml"),
    readSource("../miniprogram/pages/issues/issues.ts"),
    readSource("../miniprogram/services/api.ts"),
  ]);

  assert.match(template, /picker[^>]*range="\{\{projectMembers\}\}"[^>]*bindchange="onOwner"/);
  assert.match(template, /R 执行负责人/);
  assert.match(source, /ownerName:\s*this\.data\.projectMembers\[Number\(event\.detail\.value\)\]/);
  assert.match(apiSource, /issue-create-proposals/);
  assert.match(source, /问题新增申请已提交/);
  assert.doesNotMatch(source, /\[saved,\s*\.\.\.this\.data\.issues\]/);
});

test("global mobile layout uses compact cards and bottom safe-area spacing", async () => {
  const styles = await readSource("../miniprogram/app.wxss");

  assert.match(styles, /padding-bottom:\s*calc\([^)]*env\(safe-area-inset-bottom\)/);
  assert.match(styles, /\.card\s*\{[^}]*margin-bottom:\s*16rpx/s);
  assert.match(styles, /\.card\s*\{[^}]*padding:\s*24rpx/s);
});

test("dashboard keeps todo upcoming and overdue visible while moving secondary filters to more", async () => {
  const [source, template, styles] = await Promise.all([
    readSource("../miniprogram/pages/dashboard/dashboard.ts"),
    readSource("../miniprogram/pages/dashboard/dashboard.wxml"),
    readSource("../miniprogram/pages/dashboard/dashboard.wxss"),
  ]);

  assert.match(template, /primaryMilestoneFilters/);
  assert.match(template, /bindtap="openMoreFilters"/);
  assert.doesNotMatch(template, /class="milestone-filters" scroll-x/);
  assert.match(source, /\["todo", "upcoming", "overdue"\]/);
  assert.match(source, /itemList\s*=\s*\["已完成", "全部"\]/);
  assert.match(styles, /\.milestone-filters\s*\{[^}]*display:\s*flex/s);
  assert.match(styles, /\.milestone-filter\s*\{[^}]*flex:\s*1\s+1\s+0/s);
  assert.match(styles, /\.milestone-filter\s*\{[^}]*width:\s*0/s);
  assert.match(styles, /\.milestone-filter\.more\s*\{[^}]*flex-grow:\s*1\.3/s);
});

test("project cards expose upcoming and overdue milestones with RACI", async () => {
  const [source, template] = await Promise.all([
    readSource("../miniprogram/pages/projects/projects.ts"),
    readSource("../miniprogram/pages/projects/projects.wxml"),
  ]);

  assert.match(source, /filterMilestones/);
  assert.match(source, /milestoneUpcomingDays/);
  assert.match(template, /近期节点/);
  assert.match(template, /逾期节点/);
  assert.match(template, /alert-raci/);
  assert.match(template, /role\.key/);
  assert.match(template, /role\.names/);
});

test("my tasks groups R and A milestones by project with four risk filters", async () => {
  const [source, template, styles, apiSource] = await Promise.all([
    readSource("../miniprogram/pages/my-tasks/my-tasks.ts"),
    readSource("../miniprogram/pages/my-tasks/my-tasks.wxml"),
    readSource("../miniprogram/pages/my-tasks/my-tasks.wxss"),
    readSource("../miniprogram/services/api.ts"),
  ]);

  assert.match(apiSource, /mobile\/my-tasks/);
  assert.match(source, /task\.risk === selectedFilter/);
  assert.match(source, /\["todo", "upcoming", "overdue", "completed"\]/);
  assert.match(source, /project\.tasks\.filter\(\(task\) => task\.risk === key\)\.length/);
  assert.match(source, /label:\s*`\$\{filterLabels\[key\]\}\s\$\{count\}`/);
  assert.match(source, /filters:\s*presentFilters\(sourceProjects\)/);
  assert.match(template, /本人角色/);
  assert.match(template, /task\.kind === 'issue'/);
  assert.match(template, /bindtap="openTask"/);
  assert.match(source, /focus_issue_id/);
  assert.match(source, /wx\.switchTab\(\{ url: "\/pages\/issues\/issues" \}\)/);
  assert.match(template, /item\.entryLabel/);
  assert.match(template, /bindtap="openProject"/);
  assert.match(styles, /\.task-filters\s*\{[^}]*display:\s*flex/s);
  assert.match(styles, /\.task-filter\s*\{[^}]*flex:\s*1\s+1\s+0/s);
  assert.match(styles, /\.task-filter\s*\{[^}]*width:\s*0/s);
  assert.match(styles, /\.task-filter\s*\{[^}]*box-sizing:\s*border-box/s);
});

test("tab bar badges expose unread messages and pending approvals", async () => {
  const [badgeSource, appSource, projectsSource, projectsTemplate] = await Promise.all([
    readSource("../miniprogram/services/tab-badges.ts"),
    readSource("../miniprogram/app.ts"),
    readSource("../miniprogram/pages/projects/projects.ts"),
    readSource("../miniprogram/pages/projects/projects.wxml"),
  ]);

  assert.match(badgeSource, /setTabBarBadge/);
  assert.match(badgeSource, /removeTabBarBadge/);
  assert.match(badgeSource, /pending_approval_count/);
  assert.match(badgeSource, /!message\.is_read/);
  assert.match(appSource, /syncTabBarBadges/);
  assert.match(projectsSource, /syncTabBarBadges/);
  assert.match(projectsTemplate, /待审批/);
  assert.match(projectsTemplate, /pending_approval_count/);
});
