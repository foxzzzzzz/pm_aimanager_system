import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const source = await readFile(new URL("../miniprogram/pages/dashboard/dashboard.ts", import.meta.url), "utf8");
function setup(api, wx = {}) {
  let page;
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports: {},
    require: (path) => path.includes("/api") ? { api } : path.includes("presentation")
      ? { presentPlan: () => "计划", formatDateTime: () => "时间" }
      : path.endsWith("config") ? { runtimeConfig: {} } : { syncTabBarBadges: async () => {} },
    Page: (value) => { page = value; }, wx,
  });
  page.data = { ...page.data, projectId: "project", proposals: [{ id: "p", can_resolve: true }] };
  page.setData = (data) => Object.assign(page.data, data);
  return page;
}
const event = { currentTarget: { dataset: { id: "p", version: 1 } } };

test("conflict independently refreshes proposals and shows latest block reason", async () => {
  const toasts = [];
  const page = setup({
    approveProposal: async () => { throw Object.assign(new Error("冲突"), { status: 409 }); },
    approvableProposals: async () => [{ id: "p", approval_block_reason: "节点计划已变化" }],
  }, { showModal: async () => ({ confirm: true }), showToast: (value) => toasts.push(value) });
  page.loadDashboard = () => { throw new Error("must not require dashboard refresh"); };
  await page.approveProposal(event);
  assert.equal(page.data.proposals[0].approval_block_reason, "节点计划已变化");
  assert.equal(toasts[0].title, "节点计划已变化");
  assert.equal(page.data.resolvingProposalId, "");
});

test("confirmation is guarded against double taps and cancellation releases guard", async () => {
  let finish;
  let modals = 0;
  const page = setup({}, { showModal: () => { modals++; return new Promise((resolve) => { finish = resolve; }); } });
  const first = page.approveProposal(event);
  const second = page.approveProposal(event);
  assert.equal(modals, 1);
  finish({ confirm: false });
  await Promise.all([first, second]);
  assert.equal(page.data.resolvingProposalId, "");
});

test("failed conflict refresh preserves proposals and original server error", async () => {
  const toasts = [];
  const page = setup({
    approveProposal: async () => { throw Object.assign(new Error("节点数据已变化"), { status: 409 }); },
    approvableProposals: async () => { throw new Error("网络异常"); },
  }, { showModal: async () => ({ confirm: true }), showToast: (value) => toasts.push(value) });
  await page.approveProposal(event);
  assert.equal(page.data.proposals[0].id, "p");
  assert.equal(toasts[0].title, "节点数据已变化");
  assert.equal(page.data.resolvingProposalId, "");
});

test("expired proposal cannot approve but can still be rejected", async () => {
  let rejections = 0;
  const page = setup({ rejectProposal: async () => { rejections++; } }, {
    showModal: async () => ({ confirm: true, content: "重新提交" }), showToast: () => {},
  });
  page.data.proposals[0].approval_block_reason = "节点已取消";
  page.loadDashboard = async () => true;
  await page.approveProposal(event);
  await page.rejectProposal(event);
  assert.equal(rejections, 1);
  assert.equal(page.data.proposals.length, 0);
});

test("approval surfaces plain WeChat transport errors and releases guard", async () => {
  const toasts = [];
  const page = setup({ approveProposal: async () => { throw { errMsg: "网络断开" }; } }, {
    showModal: async () => ({ confirm: true }), showToast: (value) => toasts.push(value),
  });
  await page.approveProposal(event);
  assert.equal(toasts[0].title, "网络断开");
  assert.equal(page.data.resolvingProposalId, "");
});

test("expired proposals display reason, disable approval and retain permission based rejection", async () => {
  const template = await readFile(new URL("../miniprogram/pages/dashboard/dashboard.wxml", import.meta.url), "utf8");
  assert.match(template, /已过期/);
  assert.match(template, /item\.approval_block_reason}}/);
  assert.match(template, /disabled="{{resolvingProposalId !== '' \|\| item\.approval_block_reason}}"[^>]*bindtap="approveProposal"/);
  assert.match(template, /wx:if="{{item.can_resolve}}" class="proposal-actions"/);
});
