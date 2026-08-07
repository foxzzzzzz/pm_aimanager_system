import {
  Alert,
  Button,
  Card,
  Checkbox,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api";
import type {
  EditableMilestone,
  EditableProjectData,
  EditableProjectMember,
  MilestoneReview,
  PlanWindow,
  ProductSpecReview,
  Project,
  ProjectChangeSet,
  ProjectDataOperation,
  ProjectReview,
} from "../types";

type EditorState = {
  resource: "product_spec" | "member" | "milestone";
  op: "add" | "replace" | "remove";
  key: string;
  value?: ProductSpecReview | EditableProjectMember | EditableMilestone;
};

function display(value: string | null) {
  return value || "—";
}

function scheduleText(window: PlanWindow) {
  if (window.state === "tbd") return "待确认";
  if (window.state === "not_applicable") return "不适用";
  if (window.start_date === window.end_date) return window.start_date;
  return `${window.start_date} → ${window.end_date}`;
}

function assignmentText(milestone: MilestoneReview, role: "R" | "A") {
  return milestone.assignments[role]?.join("、") || "—";
}

export default function ProjectReviewPage({
  project,
  onPublished,
}: {
  project?: Project;
  onPublished?: () => void;
}) {
  const [review, setReview] = useState<ProjectReview>();
  const [onlyTbd, setOnlyTbd] = useState(false);
  const [error, setError] = useState<string>();
  const [editor, setEditor] = useState<EditorState>();
  const [pendingChangeSet, setPendingChangeSet] = useState<ProjectChangeSet>();
  const [editableData, setEditableData] = useState<EditableProjectData>();
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    setReview(undefined);
    setOnlyTbd(false);
    setError(undefined);
    setEditor(undefined);
    setPendingChangeSet(undefined);
    if (!project) return;
    api.projectReview(project.id).then(setReview).catch((reason: Error) => setError(reason.message));
  }, [project?.id]);

  const milestones = useMemo(
    () => review?.milestones.filter((item) => !onlyTbd || item.schedule.state === "tbd") ?? [],
    [onlyTbd, review],
  );

  const openProductEditor = async (
    op: EditorState["op"],
    item?: ProductSpecReview,
  ) => {
    if (!project) return;
    try {
      const editable = await api.projectEditableData(project.id);
      setEditableData(editable);
      const fullItem = item
        ? editable.product_specs.find((candidate) => candidate.row_number === item.row_number)
        : undefined;
      const rowNumber = fullItem?.row_number
        ?? Math.max(0, ...editable.product_specs.map((candidate) => candidate.row_number)) + 1;
      form.resetFields();
      form.setFieldsValue({
        row_number: rowNumber,
        major_category: fullItem?.major_category,
        category: fullItem?.category,
        item: fullItem?.item,
        configuration: fullItem?.configuration,
        core_information: fullItem?.core_information,
        selected_model: fullItem?.selected_model,
        notes: fullItem?.notes,
        reason: "",
      });
      setEditor({
        resource: "product_spec",
        op,
        key: String(rowNumber),
        value: fullItem,
      });
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  const openMemberEditor = async (
    op: EditorState["op"],
    memberName?: string,
  ) => {
    if (!project) return;
    try {
      const editable = await api.projectEditableData(project.id);
      setEditableData(editable);
      const member = memberName
        ? editable.members.find((candidate) => candidate.name === memberName)
        : undefined;
      form.resetFields();
      form.setFieldsValue({
        name: member?.name,
        role: member?.role,
        phone: member?.phone,
        email: member?.email,
        notes: member?.notes,
        reason: "",
      });
      setEditor({ resource: "member", op, key: memberName ?? "new-member", value: member });
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  const openMilestoneEditor = async (
    op: EditorState["op"],
    milestoneCode?: string,
  ) => {
    if (!project) return;
    try {
      const editable = await api.projectEditableData(project.id);
      setEditableData(editable);
      const milestone = milestoneCode
        ? editable.milestones.find((candidate) => candidate.code === milestoneCode)
        : undefined;
      const activePlan = editable.plan_versions.find(
        (plan) => plan.name === editable.active_plan_name,
      );
      const schedule = milestone
        ? activePlan?.milestones[milestone.name]
        : { state: "tbd", start_date: null, end_date: null };
      form.resetFields();
      form.setFieldsValue({
        code: milestone?.code,
        name: milestone?.name,
        output: milestone?.output,
        risk_note: milestone?.risk_note,
        schedule_state: schedule?.state ?? "tbd",
        start_date: schedule?.start_date,
        end_date: schedule?.end_date,
        R: milestone?.assignments.R?.join("、"),
        A: milestone?.assignments.A?.join("、"),
        C: milestone?.assignments.C?.join("、"),
        I: milestone?.assignments.I?.join("、"),
        reason: "",
      });
      setEditor({
        resource: "milestone",
        op,
        key: milestoneCode ?? "new-milestone",
        value: milestone,
      });
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  const namesFromInput = (value?: string) =>
    value?.split(/[,，、]/).map((name) => name.trim()).filter(Boolean) ?? [];

  const createPreview = async () => {
    if (!project || !review || !editor) return;
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      const operations: ProjectDataOperation[] = [];
      if (editor.resource === "product_spec") {
        const current = editor.value as ProductSpecReview | undefined;
        operations.push(editor.op === "remove"
          ? { op: "remove", resource: "product_spec", key: editor.key }
          : {
              op: editor.op,
              resource: "product_spec",
              key: editor.op === "add" ? String(values.row_number) : editor.key,
              value: {
                row_number: Number(values.row_number),
                major_category: values.major_category || null,
                category: values.category || null,
                item: values.item,
                configuration: values.configuration || null,
                core_information: values.core_information || null,
                selected_model: values.selected_model || null,
                notes: values.notes || null,
                check_confirmation: current?.check_confirmation ?? null,
                check_content: current?.check_content ?? null,
              },
            });
      } else if (editor.resource === "member") {
        const current = editor.value as EditableProjectMember | undefined;
        operations.push(editor.op === "remove"
          ? { op: "remove", resource: "member", key: editor.key }
          : {
              op: editor.op,
              resource: "member",
              key: editor.op === "add" ? values.name : editor.key,
              value: {
                name: values.name,
                role: values.role,
                phone: values.phone || current?.phone || null,
                email: values.email || current?.email || null,
                notes: values.notes || null,
              },
            });
        if (editableData && current && (editor.op === "remove" || values.name !== current.name)) {
          const replacementName = editor.op === "remove" ? undefined : String(values.name);
          for (const milestone of editableData.milestones) {
            let changed = false;
            const assignments = Object.fromEntries(
              (["R", "A", "C", "I"] as const).map((role) => [
                role,
                milestone.assignments[role].flatMap((name) => {
                  if (name !== current.name) return [name];
                  changed = true;
                  return replacementName ? [replacementName] : [];
                }),
              ]),
            ) as Record<"R" | "A" | "C" | "I", string[]>;
            if (changed) {
              operations.push({
                op: "replace",
                resource: "raci",
                key: milestone.code,
                value: assignments,
              });
            }
          }
        }
      } else if (editableData) {
        const current = editor.value as EditableMilestone | undefined;
        const code = editor.op === "add" ? values.code : editor.key;
        const name = values.name;
        const schedule: PlanWindow = values.schedule_state === "scheduled"
          ? { state: "scheduled", start_date: values.start_date, end_date: values.end_date }
          : { state: values.schedule_state, start_date: null, end_date: null };
        if (editor.op === "remove") {
          operations.push({ op: "remove", resource: "milestone", key: editor.key });
        } else {
          operations.push({
            op: editor.op,
            resource: "milestone",
            key: code,
            value: {
              code,
              name,
              output: values.output || null,
              actual_completion: current?.actual_completion
                ?? { state: "tbd", start_date: null, end_date: null },
              variance_days: current?.variance_days ?? null,
              variance_note: current?.variance_note ?? null,
              risk_note: values.risk_note || null,
              assignments: current?.assignments ?? {},
            },
          });
          operations.push({
            op: "replace",
            resource: "raci",
            key: code,
            value: {
              R: namesFromInput(values.R),
              A: namesFromInput(values.A),
              C: namesFromInput(values.C),
              I: namesFromInput(values.I),
            },
          });
        }
        for (const plan of editableData.plan_versions) {
          const milestones = { ...plan.milestones };
          if (current) delete milestones[current.name];
          if (editor.op !== "remove") {
            milestones[name] = plan.name === editableData.active_plan_name
              ? schedule
              : current
                ? plan.milestones[current.name]
                : { state: "tbd", start_date: null, end_date: null };
          }
          operations.push({
            op: "replace",
            resource: "plan",
            key: plan.name,
            value: { ...plan, milestones },
          });
        }
      }
      const changeSet = await api.createProjectChangeSet(project.id, {
        base_version_number: review.current_version_number,
        reason: values.reason,
        operations,
      });
      setPendingChangeSet(changeSet);
      setEditor(undefined);
    } catch (reason) {
      if (reason instanceof Error) setError(reason.message);
    } finally {
      setSubmitting(false);
    }
  };

  const publishChangeSet = async () => {
    if (!project || !pendingChangeSet) return;
    try {
      setSubmitting(true);
      await api.publishProjectChangeSet(
        pendingChangeSet.id,
        pendingChangeSet.base_version_number,
      );
      setPendingChangeSet(undefined);
      setReview(await api.projectReview(project.id));
      onPublished?.();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const cancelChangeSet = async () => {
    if (!pendingChangeSet) return;
    try {
      setSubmitting(true);
      await api.cancelProjectChangeSet(pendingChangeSet.id);
      setPendingChangeSet(undefined);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const editorResourceLabel = editor?.resource === "member"
    ? "团队成员"
    : editor?.resource === "milestone"
      ? "里程碑与RACI"
      : "产品规格";
  const editorActionLabel = editor?.op === "add" ? "新增" : editor?.op === "remove" ? "删除" : "修正";
  const editorSummary = editor?.resource === "product_spec"
    ? (editor.value as ProductSpecReview | undefined)?.item
    : editor?.resource === "member"
      ? (editor.value as EditableProjectMember | undefined)?.name
      : (editor?.value as EditableMilestone | undefined)?.name;

  if (!project) return <Empty description="请先选择项目" />;
  if (error) return <Alert type="error" message={error} showIcon />;
  if (!review) return <Card loading />;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <div>
        <Typography.Text type="secondary">
          正式版本 v{review.current_version_number} · 文档 {review.document_version ?? "—"}
        </Typography.Text>
        <Typography.Title level={2}>项目数据核对</Typography.Title>
      </div>
      <Alert
        type="info"
        showIcon
        message="本页展示当前已发布版本；可在后台创建变更集修正，也可更新Excel后重新导入。所有修正均需确认差异并发布新版本。"
      />
      <Tabs
        items={[
          {
            key: "specs",
            label: `产品规格 ${review.product_specs.length}`,
            children: (
              <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                <Button type="primary" onClick={() => openProductEditor("add")}>新增规格</Button>
                <Table
                  rowKey="row_number"
                  dataSource={review.product_specs}
                  pagination={{ defaultPageSize: 10 }}
                  scroll={{ x: 1250 }}
                  columns={[
                    { title: "大类", dataIndex: "major_category", render: display },
                    { title: "分类", dataIndex: "category", render: display },
                    { title: "规格项", dataIndex: "item" },
                    { title: "配置/参数", dataIndex: "configuration", render: display },
                    { title: "核心信息", dataIndex: "core_information", render: display },
                    { title: "选型", dataIndex: "selected_model", render: display },
                    { title: "备注", dataIndex: "notes", render: display },
                    {
                      title: "操作",
                      fixed: "right",
                      width: 120,
                      render: (_: unknown, item: ProductSpecReview) => (
                        <Space size="small">
                          <Button type="link" onClick={() => openProductEditor("replace", item)}>修正</Button>
                          <Button danger type="link" onClick={() => openProductEditor("remove", item)}>删除</Button>
                        </Space>
                      ),
                    },
                  ]}
                />
              </Space>
            ),
          },
          {
            key: "members",
            label: `团队成员 ${review.members.length}`,
            children: (
              <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                <Button type="primary" onClick={() => openMemberEditor("add")}>新增成员</Button>
                <Table
                  rowKey="name"
                  dataSource={review.members}
                  pagination={{ defaultPageSize: 10 }}
                  columns={[
                    { title: "成员", dataIndex: "name" },
                    { title: "岗位/角色", dataIndex: "role" },
                    { title: "备注", dataIndex: "notes", render: display },
                    {
                      title: "操作",
                      width: 120,
                      render: (_: unknown, item: { name: string }) => (
                        <Space size="small">
                          <Button type="link" onClick={() => openMemberEditor("replace", item.name)}>修正</Button>
                          <Button danger type="link" onClick={() => openMemberEditor("remove", item.name)}>删除</Button>
                        </Space>
                      ),
                    },
                  ]}
                />
              </Space>
            ),
          },
          {
            key: "milestones",
            label: `里程碑与RACI ${review.milestones.length}`,
            children: (
              <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                <Button type="primary" onClick={() => openMilestoneEditor("add")}>新增里程碑</Button>
                <Alert
                  type={review.tbd_count > 0 ? "warning" : "success"}
                  showIcon
                  message={`待确认节点 ${review.tbd_count} 个`}
                  description={`当前计划：${review.active_plan_name ?? "—"}`}
                />
                <Checkbox checked={onlyTbd} onChange={(event) => setOnlyTbd(event.target.checked)}>
                  仅显示待确认节点
                </Checkbox>
                <Table
                  rowKey="code"
                  dataSource={milestones}
                  pagination={{ defaultPageSize: 10 }}
                  scroll={{ x: 1100 }}
                  columns={[
                    { title: "编号", dataIndex: "code", width: 90 },
                    { title: "节点", dataIndex: "name" },
                    { title: "计划时间", dataIndex: "schedule", render: scheduleText },
                    {
                      title: "状态",
                      dataIndex: "schedule",
                      render: (window: PlanWindow) => (
                        <Tag color={window.state === "tbd" ? "gold" : "green"}>
                          {window.state === "tbd" ? "待确认" : window.state === "scheduled" ? "已排期" : "不适用"}
                        </Tag>
                      ),
                    },
                    { title: "R负责人", render: (_: unknown, item: MilestoneReview) => assignmentText(item, "R") },
                    { title: "A责任人", render: (_: unknown, item: MilestoneReview) => assignmentText(item, "A") },
                    { title: "交付物", dataIndex: "output", render: display },
                    { title: "风险备注", dataIndex: "risk_note", render: display },
                    {
                      title: "操作",
                      fixed: "right",
                      width: 120,
                      render: (_: unknown, item: MilestoneReview) => (
                        <Space size="small">
                          <Button type="link" onClick={() => openMilestoneEditor("replace", item.code)}>修正</Button>
                          <Button danger type="link" onClick={() => openMilestoneEditor("remove", item.code)}>删除</Button>
                        </Space>
                      ),
                    },
                  ]}
                />
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title={`${editorActionLabel}${editorResourceLabel}`}
        open={Boolean(editor)}
        okText="生成差异预览"
        cancelText="取消"
        confirmLoading={submitting}
        onOk={createPreview}
        onCancel={() => setEditor(undefined)}
      >
        <Form form={form} layout="vertical">
          {editor?.resource === "product_spec" && editor.op !== "remove" && (
            <>
              <Form.Item name="row_number" label="行号" rules={[{ required: true }]}>
                <InputNumber disabled={editor?.op === "replace"} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="major_category" label="大类"><Input /></Form.Item>
              <Form.Item name="category" label="分类"><Input /></Form.Item>
              <Form.Item name="item" label="规格项" rules={[{ required: true }]}><Input /></Form.Item>
              <Form.Item name="configuration" label="配置/参数"><Input /></Form.Item>
              <Form.Item name="core_information" label="核心信息"><Input /></Form.Item>
              <Form.Item name="selected_model" label="选型"><Input /></Form.Item>
              <Form.Item name="notes" label="备注"><Input.TextArea /></Form.Item>
            </>
          )}
          {editor?.resource === "member" && editor.op !== "remove" && (
            <>
              <Form.Item name="name" label="成员姓名" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="role" label="岗位/角色" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="phone" label="手机号"><Input /></Form.Item>
              <Form.Item name="email" label="邮箱"><Input /></Form.Item>
              <Form.Item name="notes" label="备注"><Input.TextArea /></Form.Item>
            </>
          )}
          {editor?.resource === "milestone" && editor.op !== "remove" && (
            <>
              <Form.Item name="code" label="节点编号" rules={[{ required: true }]}>
                <Input disabled={editor.op === "replace"} />
              </Form.Item>
              <Form.Item name="name" label="节点名称" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="output" label="交付物"><Input /></Form.Item>
              <Form.Item name="risk_note" label="风险备注"><Input.TextArea /></Form.Item>
              <Form.Item name="schedule_state" label="计划状态" rules={[{ required: true }]}>
                <Select options={[
                  { value: "scheduled", label: "已排期" },
                  { value: "tbd", label: "待确认" },
                  { value: "not_applicable", label: "不适用" },
                ]} />
              </Form.Item>
              <Form.Item noStyle shouldUpdate={(before, after) => before.schedule_state !== after.schedule_state}>
                {({ getFieldValue }) => getFieldValue("schedule_state") === "scheduled" && (
                  <Space style={{ width: "100%" }} align="start">
                    <Form.Item name="start_date" label="开始日期" rules={[{ required: true }]}>
                      <Input type="date" />
                    </Form.Item>
                    <Form.Item name="end_date" label="结束日期" rules={[{ required: true }]}>
                      <Input type="date" />
                    </Form.Item>
                  </Space>
                )}
              </Form.Item>
              <Typography.Text type="secondary">RACI姓名使用顿号、逗号或中文逗号分隔</Typography.Text>
              <Form.Item name="R" label="R执行者"><Input /></Form.Item>
              <Form.Item name="A" label="A最终负责人"><Input /></Form.Item>
              <Form.Item name="C" label="C协作者"><Input /></Form.Item>
              <Form.Item name="I" label="I知情人"><Input /></Form.Item>
            </>
          )}
          {editor?.op === "remove" && (
            <Alert type="warning" showIcon message={`将从新版本移除：${editorSummary ?? editor.key}`} />
          )}
          <Form.Item
            name="reason"
            label="变更原因"
            rules={[{ required: true, message: "请输入变更原因" }]}
          >
            <Input.TextArea />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title={`变更差异预览（基线 v${pendingChangeSet?.base_version_number ?? "—"}）`}
        open={Boolean(pendingChangeSet)}
        okText="确认发布"
        cancelText="取消变更"
        confirmLoading={submitting}
        onOk={publishChangeSet}
        onCancel={cancelChangeSet}
      >
        <Typography.Paragraph>变更原因：{pendingChangeSet?.reason}</Typography.Paragraph>
        <Table
          rowKey="path"
          size="small"
          pagination={false}
          dataSource={pendingChangeSet?.diff ?? []}
          columns={[
            { title: "字段", dataIndex: "path" },
            { title: "操作", dataIndex: "operation" },
            { title: "前值", dataIndex: "before", render: (value) => JSON.stringify(value) },
            { title: "后值", dataIndex: "after", render: (value) => JSON.stringify(value) },
          ]}
        />
      </Modal>
    </Space>
  );
}
