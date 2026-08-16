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

test("issue page switches bound projects in a native selection sheet", async () => {
  const source = await readSource("../miniprogram/pages/issues/issues.ts");

  const selection = source.match(/async selectProject\(\)[\s\S]*?\n  },\n  openCreateForm/);
  assert.match(selection?.[0] ?? "", /api\.projects\(\)/);
  assert.match(selection?.[0] ?? "", /wx\.showActionSheet/);
  assert.match(selection?.[0] ?? "", /current_project_id/);
  assert.match(selection?.[0] ?? "", /await this\.loadIssues\(\)/);
  assert.doesNotMatch(selection?.[0] ?? "", /switchTab/);
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

test("issue form and cards expose complete RACI and risk state", async () => {
  const [source, template] = await Promise.all([
    readSource("../miniprogram/pages/issues/issues.ts"),
    readSource("../miniprogram/pages/issues/issues.wxml"),
  ]);

  assert.match(source, /accountableNames/);
  assert.match(source, /consultedNames/);
  assert.match(source, /informedNames/);
  assert.match(template, /A 最终负责人/);
  assert.match(template, /C 协作\/咨询/);
  assert.match(template, /I 知情/);
  assert.match(template, /item\.riskLabel/);
  assert.match(template, /item\.accountableLabel/);
  assert.doesNotMatch(template, /\.join\(/);
});

test("issue editing keeps A C and I selectable and submits changed RACI", async () => {
  const [source, template] = await Promise.all([
    readSource("../miniprogram/pages/issues/issues.ts"),
    readSource("../miniprogram/pages/issues/issues.wxml"),
  ]);

  assert.doesNotMatch(template, /wx:if="\{\{!editingIssueId\}\}" class="field-block"/);
  assert.doesNotMatch(template, /wx:if="\{\{!editingIssueId\}\}" range="\{\{projectMembers\}\}"/);
  assert.match(template, /checked="\{\{member\.checked\}\}"/);
  assert.match(source, /owner_name:\s*this\.data\.ownerName/);
  assert.match(source, /accountable_names:\s*this\.data\.accountableNames/);
  assert.match(source, /consulted_names:\s*this\.data\.consultedNames/);
  assert.match(source, /informed_names:\s*this\.data\.informedNames/);
});

test("issue and approval cards expose complete details and both timestamps", async () => {
  const [issueTemplate, dashboardTemplate, dashboardSource, detailTemplate, appConfig] = await Promise.all([
    readSource("../miniprogram/pages/issues/issues.wxml"),
    readSource("../miniprogram/pages/dashboard/dashboard.wxml"),
    readSource("../miniprogram/pages/dashboard/dashboard.ts"),
    readSource("../miniprogram/pages/issue-approval-detail/issue-approval-detail.wxml"),
    readSource("../miniprogram/app.json"),
  ]);

  assert.match(issueTemplate, /提交时间：\{\{item\.createdAtLabel\}\}/);
  assert.match(issueTemplate, /完成时间：\{\{item\.dueDateLabel\}\}/);
  assert.match(dashboardTemplate, /bindtap="showIssueCreateDetail"/);
  assert.match(dashboardTemplate, /bindtap="showIssueDeleteDetail"/);
  assert.match(dashboardTemplate, /完成时间：\{\{item\.dueDateLabel\}\}/);
  assert.match(dashboardTemplate, /class="approval-raci"/);
  assert.match(dashboardSource, /showIssueCreateDetail/);
  assert.match(dashboardSource, /showIssueDeleteDetail/);
  assert.match(dashboardSource, /wx\.navigateTo/);
  assert.match(appConfig, /pages\/issue-approval-detail\/issue-approval-detail/);
  assert.match(detailTemplate, /问题影响/);
  assert.match(detailTemplate, /A 最终负责人/);
  assert.match(detailTemplate, /删除原因/);
});

test("issue deletion submits an approval request and managers can resolve it", async () => {
  const [issuesSource, dashboardSource, dashboardTemplate, presentationSource] = await Promise.all([
    readSource("../miniprogram/pages/issues/issues.ts"),
    readSource("../miniprogram/pages/dashboard/dashboard.ts"),
    readSource("../miniprogram/pages/dashboard/dashboard.wxml"),
    readSource("../miniprogram/services/presentation.js"),
  ]);

  assert.match(issuesSource, /删除申请已提交/);
  assert.match(dashboardSource, /issueDeleteProposals/);
  assert.match(dashboardSource, /approveIssueDeleteProposal/);
  assert.match(dashboardSource, /rejectIssueDeleteProposal/);
  assert.match(dashboardSource, /resolvingIssueProposalId/);
  assert.match(dashboardSource, /审批已通过/);
  assert.match(dashboardTemplate, /待审批删除问题/);
  assert.match(dashboardTemplate, /批准删除/);
  assert.match(dashboardTemplate, /暂无待审批的问题申请/);
  assert.match(dashboardTemplate, /dashboard\.is_project_manager/);
  assert.match(presentationSource, /issue_create_approved:\s*"新增审批通过"/);
  assert.match(presentationSource, /issue_delete_rejected:\s*"删除审批驳回"/);
});

test("issue cancellation starts with an empty reason field", async () => {
  const source = await readSource("../miniprogram/pages/issues/issues.ts");

  const cancellationModal = source.match(/async deleteIssue[\s\S]*?confirmColor:\s*"#c53030"/);
  assert.match(cancellationModal?.[0] ?? "", /editable:\s*true/);
  assert.match(cancellationModal?.[0] ?? "", /placeholderText:\s*""/);
});
