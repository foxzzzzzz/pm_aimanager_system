import type { IssueCreateProposal, IssueDeleteProposal } from "../../types";

type ApprovalDetail =
  | { kind: "create"; proposal: IssueCreateProposal }
  | { kind: "delete"; proposal: IssueDeleteProposal };

Page({
  data: {
    detail: null as ApprovalDetail | null,
    issue: null as IssueCreateProposal["payload"] | IssueDeleteProposal["issue"] | null,
    approvalTypeLabel: "",
    accountableLabel: "",
    consultedLabel: "",
    informedLabel: "",
    deleteReason: "",
  },
  onLoad() {
    const detail = wx.getStorageSync<ApprovalDetail>("issue_approval_detail");
    if (!detail?.proposal) return;
    const issue = detail.kind === "create" ? detail.proposal.payload : detail.proposal.issue;
    this.setData({
      detail,
      issue,
      approvalTypeLabel: detail.kind === "create" ? "重点问题新增申请" : "重点问题删除申请",
      accountableLabel: issue.accountable_names.join("、") || "—",
      consultedLabel: issue.consulted_names.join("、") || "—",
      informedLabel: issue.informed_names.join("、") || "—",
      deleteReason: detail.kind === "delete" ? detail.proposal.reason : "",
    });
  },
});
