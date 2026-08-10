import { Alert, Button, DatePicker, Empty, Form, Image, Input, Modal, Select, Space, Table, Tabs, Tag, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { AuditLog, ChangeProposal, Issue, MemberBinding, MemberInvitation, Project } from "../types";

interface Props {
  project?: Project;
}

interface IssueForm {
  description: string;
  impact: string;
  owner_name: string;
  severity: string;
  due_date: Dayjs;
  status?: string;
}

interface InvitationForm { member_name: string; expected_phone?: string }

export default function IssuesAuditPage({ project }: Props) {
  const [issues, setIssues] = useState<Issue[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [bindings, setBindings] = useState<MemberBinding[]>([]);
  const [proposals, setProposals] = useState<ChangeProposal[]>([]);
  const [open, setOpen] = useState(false);
  const [editingIssue, setEditingIssue] = useState<Issue>();
  const [deletingIssue, setDeletingIssue] = useState<Issue>();
  const [deleteReason, setDeleteReason] = useState("");
  const [invitationOpen, setInvitationOpen] = useState(false);
  const [invitation, setInvitation] = useState<MemberInvitation>();
  const [error, setError] = useState<string>();
  const [form] = Form.useForm<IssueForm>();
  const [invitationForm] = Form.useForm<InvitationForm>();
  const reloadSequence = useRef(0);

  const reload = async () => {
    if (!project) return;
    const sequence = ++reloadSequence.current;
    try {
      const [nextIssues, nextAudit, nextBindings, nextProposals] = await Promise.all([
        api.listIssues(project.id),
        api.listAuditLogs(project.id),
        api.listMemberBindings(project.id),
        api.listChangeProposals(project.id),
      ]);
      if (sequence !== reloadSequence.current) return;
      setIssues(nextIssues);
      setAuditLogs(nextAudit);
      setBindings(nextBindings);
      setProposals(nextProposals);
      setError(undefined);
    } catch (reason) {
      if (sequence === reloadSequence.current) setError((reason as Error).message);
    }
  };

  useEffect(() => {
    void reload();
    return () => { reloadSequence.current += 1; };
  }, [project]);

  if (!project) return <Empty description="请先选择项目" />;

  const submit = async () => {
    const values = await form.validateFields();
    if (editingIssue) {
      await api.updateIssue(editingIssue.id, {
        expected_revision: editingIssue.revision,
        ...values,
        due_date: values.due_date.format("YYYY-MM-DD"),
      });
    } else {
      await api.createIssue(project.id, {
        ...values,
        due_date: values.due_date.format("YYYY-MM-DD"),
      });
    }
    setOpen(false);
    setEditingIssue(undefined);
    form.resetFields();
    await reload();
  };

  const openIssueEditor = (issue: Issue) => {
    setEditingIssue(issue);
    form.setFieldsValue({
      description: issue.description,
      impact: issue.impact,
      owner_name: issue.owner_name,
      severity: issue.severity,
      due_date: dayjs(issue.due_date),
      status: issue.status,
    });
    setOpen(true);
  };

  const deleteIssue = async () => {
    if (!deletingIssue || !deleteReason.trim()) return;
    await api.deleteIssue(deletingIssue.id, deletingIssue.revision, deleteReason.trim());
    setDeletingIssue(undefined);
    setDeleteReason("");
    await reload();
  };

  const approveBinding = async (bindingId: string) => {
    await api.approveMemberBinding(bindingId);
    await reload();
  };

  const resolveProposal = async (proposal: ChangeProposal, approve: boolean) => {
    if (approve) await api.approveChangeProposal(proposal);
    else await api.rejectChangeProposal(proposal.id, "项目经理驳回");
    await reload();
  };

  const createInvitation = async () => {
    const values = await invitationForm.validateFields();
    try {
      const result = await api.createMemberInvitation(project.id, values);
      setInvitation(result);
      await reload();
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  const copyInvitation = async () => {
    if (!invitation) return;
    try {
      await navigator.clipboard.writeText(invitation.url_link ?? invitation.mini_program_path);
    } catch (reason) {
      setError((reason as Error).message || "复制邀请入口失败");
    }
  };

  return (
    <div className="page-stack">
      {error && <Alert type="error" message={error} showIcon closable onClose={() => setError(undefined)} />}
      <div className="page-heading">
        <Typography.Title level={2}>问题与审计</Typography.Title>
        <Button type="primary" onClick={() => { setEditingIssue(undefined); form.resetFields(); setOpen(true); }}>登记问题</Button>
      </div>
      <Tabs
        items={[
          {
            key: "issues",
            label: `重难点问题 ${issues.length}`,
            children: (
              <Table
                rowKey="id"
                dataSource={issues}
                columns={[
                  { title: "问题", dataIndex: "description" },
                  { title: "影响", dataIndex: "impact" },
                  { title: "责任人", dataIndex: "owner_name" },
                  { title: "完成时间", dataIndex: "due_date" },
                  { title: "状态", dataIndex: "status", render: (value: string) => <Tag>{value}</Tag> },
                  {
                    title: "操作",
                    render: (_value: unknown, issue: Issue) => (
                      <Space>
                        <Button size="small" onClick={() => openIssueEditor(issue)}>编辑</Button>
                        <Button
                          size="small"
                          danger
                          disabled={issue.status === "已关闭"}
                          onClick={() => { setDeletingIssue(issue); setDeleteReason(""); }}
                        >删除</Button>
                      </Space>
                    ),
                  },
                ]}
              />
            ),
          },
          {
            key: "bindings",
            label: `成员绑定 ${bindings.length}`,
            children: (
              <Space direction="vertical" style={{ width: "100%" }}>
              <Button onClick={() => { invitationForm.resetFields(); setInvitation(undefined); setInvitationOpen(true); }}>生成邀请</Button>
              <Table
                rowKey="id"
                dataSource={bindings}
                columns={[
                  { title: "成员", dataIndex: "member_name" },
                  { title: "邀请手机号", dataIndex: "expected_phone", render: (value: string | null) => value ?? "—" },
                  { title: "授权手机号", dataIndex: "provided_phone", render: (value: string | null) => value ?? "—" },
                  { title: "状态", dataIndex: "status", render: (value: string) => <Tag>{value}</Tag> },
                  {
                    title: "操作",
                    render: (_value: unknown, binding: MemberBinding) => binding.status === "pending_review"
                      ? <Button size="small" onClick={() => approveBinding(binding.id)}>通过</Button>
                      : "—",
                  },
                ]}
              />
              </Space>
            ),
          },
          {
            key: "proposals",
            label: `变更审批 ${proposals.filter((item) => item.status === "pending").length}`,
            children: (
              <Table
                rowKey="id"
                dataSource={proposals}
                columns={[
                  { title: "节点", dataIndex: "milestone_code" },
                  { title: "类型", dataIndex: "kind" },
                  { title: "原因", dataIndex: "reason" },
                  { title: "状态", dataIndex: "status", render: (value: string) => <Tag>{value}</Tag> },
                  {
                    title: "操作",
                    render: (_value: unknown, proposal: ChangeProposal) => proposal.status === "pending" ? (
                      <Space>
                        <Button size="small" type="primary" onClick={() => resolveProposal(proposal, true)}>通过</Button>
                        <Button size="small" danger onClick={() => resolveProposal(proposal, false)}>驳回</Button>
                      </Space>
                    ) : "—",
                  },
                ]}
              />
            ),
          },
          {
            key: "audit",
            label: `审计记录 ${auditLogs.length}`,
            children: (
              <Table
                rowKey="id"
                dataSource={auditLogs}
                columns={[
                  { title: "时间", dataIndex: "created_at", render: (value: string) => dayjs(value).format("YYYY-MM-DD HH:mm") },
                  { title: "操作", dataIndex: "action" },
                  { title: "操作者", dataIndex: "actor_id" },
                  { title: "原因", dataIndex: "reason", render: (value: string | null) => value ?? "—" },
                ]}
              />
            ),
          },
        ]}
      />
      <Modal title={editingIssue ? "编辑重难点问题" : "登记重难点问题"} open={open} onCancel={() => { setOpen(false); setEditingIssue(undefined); }} onOk={submit} okText="保存">
        <Form form={form} layout="vertical">
          <Form.Item name="description" label="问题描述" rules={[{ required: true }]}><Input.TextArea /></Form.Item>
          <Form.Item name="impact" label="项目影响" rules={[{ required: true }]}><Input.TextArea /></Form.Item>
          <Space align="start">
            <Form.Item name="owner_name" label="责任人" rules={[{ required: true }]}><Input /></Form.Item>
            <Form.Item name="severity" label="严重程度" initialValue="high" rules={[{ required: true }]}>
              <Select style={{ width: 120 }} options={[
                { value: "low", label: "低" },
                { value: "medium", label: "中" },
                { value: "high", label: "高" },
                { value: "critical", label: "重大" },
              ]} />
            </Form.Item>
            <Form.Item name="due_date" label="预计完成" rules={[{ required: true }]}><DatePicker /></Form.Item>
          </Space>
          {editingIssue && (
            <Form.Item name="status" label="状态" rules={[{ required: true }]}>
              <Select options={["待处理", "处理中", "待验证", "已解决", "已关闭"].map((value) => ({ value, label: value }))} />
            </Form.Item>
          )}
        </Form>
      </Modal>
      <Modal
        title="删除问题（版本化关闭）"
        open={Boolean(deletingIssue)}
        okText="确认删除"
        cancelText="取消"
        okButtonProps={{ disabled: !deleteReason.trim(), danger: true }}
        onOk={deleteIssue}
        onCancel={() => {
          setDeletingIssue(undefined);
          setDeleteReason("");
        }}
      >
        <Alert type="warning" showIcon message="该操作会将问题标记为已关闭，历史和审计记录仍保留。" />
        <Form layout="vertical">
          <Form.Item label="删除原因" htmlFor="issue-delete-reason" required>
            <Input.TextArea
              id="issue-delete-reason"
              value={deleteReason}
              onChange={(event) => setDeleteReason(event.target.value)}
            />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title="生成成员邀请"
        open={invitationOpen}
        onCancel={() => setInvitationOpen(false)}
        onOk={() => invitation ? setInvitationOpen(false) : void createInvitation()}
        okText={invitation ? "关闭" : "确认生成"}
      >
        <Form form={invitationForm} layout="vertical" hidden={Boolean(invitation)}>
          <Form.Item name="member_name" label="成员姓名" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="expected_phone" label="手机号（可选）">
            <Input />
          </Form.Item>
        </Form>
        {invitation && (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Typography.Text strong>邀请入口（请在有效期内使用）</Typography.Text>
            <Space.Compact block>
              <Input
                aria-label="邀请链接"
                readOnly
                value={invitation.url_link ?? invitation.mini_program_path}
              />
              <Button aria-label="复制邀请入口" onClick={() => void copyInvitation()}>复制</Button>
            </Space.Compact>
            {invitation.mini_program_code_data_url && (
              <Image
                width={220}
                src={invitation.mini_program_code_data_url}
                alt="成员邀请小程序码"
                preview={false}
              />
            )}
            {invitation.entry_generation_error && (
              <Alert
                type="warning"
                showIcon
                message="正式邀请链接或小程序码暂不可用"
                description={`${invitation.entry_generation_error}；可在开发者工具中使用上述小程序路径调试。`}
              />
            )}
          </Space>
        )}
      </Modal>
    </div>
  );
}
