import { Alert, Button, Card, Checkbox, Empty, Input, Select, Skeleton, Space, Table, Tag, Typography } from "antd";
import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { PlanWindow, Project, RetrospectiveOptions, RetrospectiveReport, RetrospectiveReview } from "../types";

const sourceLabels: Record<string, string> = { excel: "Excel 发布", admin_web: "后台发布", mobile: "小程序审批", pre_import_history: "导入前历史", unknown: "来源未采集" };
const kindLabels: Record<string, string> = { schedule: "计划调整", completion: "完成记录", scope: "范围变化" };
const statusLabels: Record<string, string> = { completed: "已完成", incomplete: "未完成", not_applicable: "不适用", removed: "已删除", approved: "已批准", rejected: "已驳回", pending: "待审批", cancelled: "已取消", published: "已发布", uncollected: "未采集", unknown: "未知" };
const windowText = (value: PlanWindow | null) => !value ? "未采集" : value.state === "not_applicable" ? "不适用" : value.end_date ?? "日期缺失";
const varianceText = (value: number | null) => value == null ? "不计算" : `${value > 0 ? "+" : ""}${value} 天`;
const evidenceText = (value: unknown): string => {
  if (value == null) return "未采集";
  if (typeof value !== "object") return String(value);
  if (Array.isArray(value)) return value.map(evidenceText).join("；");
  const item = value as Record<string, unknown>;
  if ("state" in item) {
    if (item.state === "not_applicable") return "不适用";
    if (item.state === "tbd") return "待定";
    return `${item.start_date ?? "开始日期缺失"} 至 ${item.end_date ?? "结束日期缺失"}`;
  }
  const labels: Record<string, string> = { code: "节点编号", name: "节点名称", status: "状态", scope_change: "范围变化", plan: "计划", actual_completion: "实际完成", start_date: "开始日期", end_date: "结束日期", added: "新增", removed: "删除", milestone_code: "节点编号", milestone_name: "节点名称" };
  return Object.entries(item).map(([key, entry]) => `${labels[key] ?? key}：${typeof entry === "string" ? statusLabels[entry] ?? labels[entry] ?? entry : evidenceText(entry)}`).join("；");
};

export default function ProjectRetrospectivePage({ project }: { project?: Project }) {
  const [reports, setReports] = useState<RetrospectiveReport[]>([]);
  const [options, setOptions] = useState<RetrospectiveOptions>();
  const [baseline, setBaseline] = useState<number>();
  const [report, setReport] = useState<RetrospectiveReport>();
  const [review, setReview] = useState<RetrospectiveReview>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [copiedReview, setCopiedReview] = useState(false);
  const generation = useRef(0);
  const selection = useRef(0);

  const showReport = (item: RetrospectiveReport) => {
    setReport(item);
    setReview(structuredClone(item.review));
    setDirty(false);
    setCopiedReview(false);
  };

  useEffect(() => {
    const current = ++generation.current;
    selection.current++;
    setReports([]); setReport(undefined); setReview(undefined); setOptions(undefined); setError(undefined); setDirty(false); setBusy(false); setCopiedReview(false);
    if (!project) return;
    setLoading(true);
    Promise.all([api.retrospectiveOptions(project.id), api.listRetrospectives(project.id)])
      .then(([nextOptions, nextReports]) => {
        if (current !== generation.current) return;
        setOptions(nextOptions); setBaseline(nextOptions.baselines.length ? 0 : undefined); setReports(nextReports);
        if (nextReports[0]) showReport(nextReports[0]);
      })
      .catch((reason: Error) => { if (current === generation.current) setError(reason.message); })
      .finally(() => { if (current === generation.current) setLoading(false); });
    return () => { generation.current++; };
  }, [project?.id]);

  const fail = (reason: Error & { status?: number }) => setError(reason.status === 409 ? `${reason.message}；请生成新草稿并重新核对。当前人工输入已保留。` : reason.message);
  const edit = (next: RetrospectiveReview) => { setReview(next); setDirty(true); };
  const mutate = async (operation: () => Promise<RetrospectiveReport>, preserveReview?: RetrospectiveReview) => {
    const current = generation.current;
    setBusy(true); setError(undefined);
    try {
      const item = await operation();
      if (current !== generation.current) return;
      showReport(item);
      if (preserveReview) {
        setReview({ ...structuredClone(preserveReview), baseline_confirmed: false, reason_reviews: preserveReview.reason_reviews.map((reason) => ({ ...reason, status: "pending" })) });
        setDirty(true); setCopiedReview(true);
      }
      setReports((items) => [item, ...items.filter(({ id }) => id !== item.id)]);
    } catch (reason) { if (current === generation.current) fail(reason as Error); }
    finally { if (current === generation.current) setBusy(false); }
  };
  const createDraft = (supersedes?: string) => {
    if (!project || !options?.baselines.length) return;
    const selected = baseline === undefined ? undefined : options?.baselines[baseline];
    const original = supersedes ? report : undefined;
    void mutate(() => api.createRetrospective(project.id, original ? { supersedes_report_id: original.id } : {
      baseline_version_number: selected?.version_number,
      baseline_plan_name: selected?.plan_name,
    }), supersedes ? review : undefined);
  };

  const saveReview = () => {
    if (!report || !review) return;
    if (review.improvements.some((item) => !item.scenario.trim() || !item.action.trim() || !item.proposed_owner.trim() || !item.acceptance.trim())) {
      setError("请补齐已登记建议的适用场景、具体动作、拟负责人和验收思路，或移除空白建议。"); return;
    }
    if (review.reason_reviews.some((reason) => reason.status === "confirmed" && (!options?.reason_categories.includes(reason.category) || !reason.confirmed_reason.trim() || !reason.evidence.trim() || !reason.fact_confirmed_by.trim() || !reason.confirmation_source.trim()))) {
      setError("已确认原因需补齐分类、原因、证据、事实确认人和意见来源；证据不足时请保留待确认。"); return;
    }
    void mutate(() => api.updateRetrospective(report.id, { ...review, expected_revision: report.revision, reason_reviews: review.reason_reviews.map(({ recorded_by: _, ...item }) => item), improvements: review.improvements.map(({ recorded_by: _, ...item }) => item) }));
  };

  if (!project) return <Empty description="请先选择项目" />;
  if (loading) return <Skeleton active />;
  const readOnly = report?.status === "confirmed";
  const nodeOptions = report?.facts.milestones.map(({ code, name }) => ({ value: code, label: `${code} · ${name}` })) ?? [];
  const field = (label: string, value: string, onChange: (value: string) => void) => (
    <label style={{ display: "grid", gap: 4 }}>{label}<Input.TextArea aria-label={label} value={value} disabled={readOnly || busy} autoSize onChange={(event) => onChange(event.target.value)} /></label>
  );

  return <div className="page-stack retrospective-page">
    <div className="page-heading"><Typography.Title level={2}>项目复盘</Typography.Title><Tag>{project.code}</Tag></div>
    {error && <Alert type="error" showIcon message={error} />}
    <Card title="报告与原始基准">
      <Space wrap>
        <Select aria-label="原始基准" placeholder="选择基准计划" style={{ minWidth: 230 }} value={baseline} onChange={setBaseline} disabled={busy}
          options={options?.baselines.map((item, index) => ({ value: index, label: `v${item.version_number} · ${item.plan_name}` }))} />
        <Button onClick={() => createDraft()} disabled={busy || !options?.baselines.length || dirty} loading={busy}>生成新草稿</Button>
        <Select aria-label="复盘报告" placeholder="选择报告" style={{ minWidth: 230 }} value={report?.id} disabled={busy || dirty}
          options={reports.map((item) => ({ value: item.id, label: `报告 ${item.report_number} · ${item.status === "confirmed" ? "已确认" : "草稿"}` }))}
          onChange={(id) => {
            const current = generation.current; const request = ++selection.current;
            setBusy(true); setError(undefined);
            api.getRetrospective(id).then((item) => { if (current === generation.current && request === selection.current) showReport(item); })
              .catch((reason: Error) => { if (current === generation.current && request === selection.current) fail(reason); })
              .finally(() => { if (current === generation.current && request === selection.current) setBusy(false); });
          }} />
      </Space>
      {options && !options.baselines.length && <Alert type="info" message="请先发布项目，再生成复盘报告。" />}
      {dirty && <Alert type="info" message="有未保存意见。请先保存；遇到快照冲突时请保留或复制意见，再生成新草稿核对。" />}
      {!report && <Empty description="暂无复盘报告，请生成草稿" />}
    </Card>
    {report && review && <>
      <Card title={`报告 ${report.report_number} · ${readOnly ? "已确认（只读）" : "草稿"}`}>
        <Space direction="vertical" style={{ width: "100%" }}>
          <Typography.Text>截止时点：{report.facts.cutoff_at}；正式版本：v{report.facts.project_version_number}；自然日口径</Typography.Text>
          <Typography.Text>原始基准：v{report.facts.baseline.version_number} · {report.facts.baseline.plan_name}；创建人：{report.created_by}</Typography.Text>
          {report.supersedes_report_id && <Alert type="warning" message={`修订自 ${report.supersedes_report_id}，复制的人工意见须重新核实。`} />}
          {copiedReview && <Alert type="warning" message="上一份报告的人工意见已保留到当前草稿，尚未保存。请重新核对基准和原因后保存。" />}
          {readOnly && <Typography.Text>确认人：{report.confirmed_by}；确认时间：{report.confirmed_at}</Typography.Text>}
          {report.facts.warnings.map((warning, index) => <Alert key={index} type="warning" message={warning} />)}
          <Checkbox aria-label="已核对原始基准" checked={review.baseline_confirmed} disabled={readOnly || busy} onChange={(event) => edit({ ...review, baseline_confirmed: event.target.checked })}>已核对原始基准</Checkbox>
          {field("基准确认依据", review.baseline_note, (value) => edit({ ...review, baseline_note: value }))}
        </Space>
      </Card>
      <Card title="进度对照">
        <Table rowKey="code" dataSource={report.facts.milestones} pagination={false} scroll={{ x: 1200 }} columns={[
          { title: "节点", render: (_, item) => `${item.code} · ${item.name}` },
          { title: "状态 / 范围", render: (_, item) => `${statusLabels[item.status] ?? item.status}${item.scope_change === "added" ? " / 新增" : item.scope_change === "removed" ? " / 删除" : ""}` },
          { title: "原始承诺结束", render: (_, item) => windowText(item.original_plan) },
          { title: "最后批准计划结束", render: (_, item) => windowText(item.latest_plan) },
          { title: "偏差采用计划结束", render: (_, item) => windowText(item.variance_plan) },
          { title: "实际完成", render: (_, item) => windowText(item.actual_completion) },
          { title: "原始偏差", dataIndex: "original_variance_days", render: varianceText },
          { title: "调整后偏差", dataIndex: "adjusted_variance_days", render: varianceText },
          { title: "生效调整次数", dataIndex: "effective_adjustment_count" },
          { title: "导入计划行数", dataIndex: "imported_plan_rows_count" },
          { title: "资料提示", render: (_, item) => item.warnings.join("；") || "—" },
        ]} />
        <Typography.Text type="secondary">调整后偏差采用完成时有效计划，完成后调整不抹去既有延期。节点偏差不相加为项目总延期；缺失日期、不适用和未完成节点不按零延期处理。</Typography.Text>
      </Card>
      <Card title="全来源变更时间线">
        {report.facts.timeline.length === 0 && <Empty description="暂无变更证据" />}
        <Space direction="vertical" style={{ width: "100%" }}>{report.facts.timeline.map((event) => <Card size="small" key={event.id} title={`${event.milestone_code ?? "项目"} · ${sourceLabels[event.source] ?? event.source} · ${kindLabels[event.kind] ?? event.kind}`}>
          <Space direction="vertical">
            <Typography.Text>{event.effective ? "已生效" : "未计入生效调整"} · {statusLabels[event.status] ?? event.status}；发生时间：{event.occurred_at ?? "未采集"}；记录时间：{event.recorded_at}</Typography.Text>
            <Typography.Text>修改前：{evidenceText(event.before)} → 修改后：{evidenceText(event.after)}</Typography.Text>
            <Typography.Text>申请人：{event.submitted_by ?? "未采集"}；审批人：{event.resolved_by ?? "未采集"}</Typography.Text>
            <Typography.Text>原始理由：<span>{event.reason ?? "未采集"}</span></Typography.Text>
            {event.evidence_refs.map((reference) => <Typography.Text key={reference}>{reference}</Typography.Text>)}
          </Space>
        </Card>)}</Space>
      </Card>
      <Card title="人工原因确认" extra={!readOnly && <Button disabled={busy} onClick={() => edit({ ...review, reason_reviews: [...review.reason_reviews, { milestone_code: nodeOptions[0]?.value ?? "", category: "", confirmed_reason: "", evidence: "", fact_confirmed_by: "", confirmation_source: "", status: "pending" }] })}>添加原因</Button>}>
        <Space direction="vertical" style={{ width: "100%" }}>{review.reason_reviews.map((reason, index) => {
          const update = (patch: Partial<typeof reason>) => edit({ ...review, reason_reviews: review.reason_reviews.map((item, current) => current === index ? { ...item, ...patch } : item) });
          return <Card size="small" key={index} title={`原因 ${index + 1}`} extra={!readOnly && <Button disabled={busy} onClick={() => edit({ ...review, reason_reviews: review.reason_reviews.filter((_, current) => current !== index) })}>移除原因</Button>}>
            <Space direction="vertical" style={{ width: "100%" }}>
              <Select aria-label={`原因节点 ${index + 1}`} value={reason.milestone_code || undefined} options={nodeOptions} disabled={readOnly || busy} onChange={(value) => update({ milestone_code: value })} style={{ minWidth: 230 }} />
              <Select aria-label={`原因分类 ${index + 1}`} placeholder="选择原因分类" value={reason.category || undefined} options={options?.reason_categories.map((value) => ({ value, label: value }))} disabled={readOnly || busy} onChange={(value) => update({ category: value })} style={{ minWidth: 230 }} />
              {field(`确认原因 ${index + 1}`, reason.confirmed_reason, (value) => update({ confirmed_reason: value }))}
              {field(`原因证据 ${index + 1}`, reason.evidence, (value) => update({ evidence: value }))}
              {field(`事实确认人 ${index + 1}`, reason.fact_confirmed_by, (value) => update({ fact_confirmed_by: value }))}
              {field(`意见来源 ${index + 1}`, reason.confirmation_source, (value) => update({ confirmation_source: value }))}
              <Checkbox checked={reason.status === "confirmed"} disabled={readOnly || busy} onChange={(event) => update({ status: event.target.checked ? "confirmed" : "pending" })}>事实和原因已人工确认</Checkbox>
              {reason.recorded_by && <Typography.Text>代录人：{reason.recorded_by}</Typography.Text>}
            </Space>
          </Card>;
        })}</Space>
      </Card>
      <Card title="改进建议登记" extra={!readOnly && <Button disabled={busy} onClick={() => edit({ ...review, improvements: [...review.improvements, { milestone_code: null, source_event_ids: [], scenario: "", action: "", proposed_owner: "", acceptance: "" }] })}>添加改进建议</Button>}>
        <Space direction="vertical" style={{ width: "100%" }}>{review.improvements.map((item, index) => {
          const update = (patch: Partial<typeof item>) => edit({ ...review, improvements: review.improvements.map((value, current) => current === index ? { ...value, ...patch } : value) });
          return <Card size="small" key={index} title={`建议 ${index + 1}`} extra={!readOnly && <Button disabled={busy} onClick={() => edit({ ...review, improvements: review.improvements.filter((_, current) => current !== index) })}>移除建议</Button>}>
            <Space direction="vertical" style={{ width: "100%" }}>
              <Select aria-label={`建议节点 ${index + 1}`} allowClear placeholder="项目级建议" value={item.milestone_code ?? undefined} options={nodeOptions} disabled={readOnly || busy} onChange={(value) => update({ milestone_code: value ?? null })} style={{ minWidth: 230 }} />
              <Select aria-label={`来源问题 ${index + 1}`} mode="multiple" placeholder="关联来源证据" value={item.source_event_ids} options={report.facts.timeline.map((event) => ({ value: event.id, label: `${event.milestone_code ?? "项目"} · ${event.reason ?? event.id}` }))} disabled={readOnly || busy} onChange={(value) => update({ source_event_ids: value })} style={{ minWidth: 300 }} />
              {field(`适用场景 ${index + 1}`, item.scenario, (value) => update({ scenario: value }))}
              {field(`具体动作 ${index + 1}`, item.action, (value) => update({ action: value }))}
              {field(`拟负责人 ${index + 1}`, item.proposed_owner, (value) => update({ proposed_owner: value }))}
              {field(`验收思路 ${index + 1}`, item.acceptance, (value) => update({ acceptance: value }))}
              {item.recorded_by && <Typography.Text>登记人：{item.recorded_by}</Typography.Text>}
            </Space>
          </Card>;
        })}</Space>
      </Card>
      <Space wrap>
        {!readOnly && <>
          <Button type="primary" disabled={busy} loading={busy} onClick={saveReview}>保存核对意见</Button>
          <Button disabled={busy || dirty || !review.baseline_confirmed} onClick={() => void mutate(() => api.confirmRetrospective(report.id, report.revision))}>确认报告</Button>
        </>}
        <Button disabled={busy || !options?.baselines.length} onClick={() => createDraft(report.id)}>{readOnly ? "创建修订草稿" : "生成新草稿并保留意见"}</Button>
      </Space>
    </>}
  </div>;
}
