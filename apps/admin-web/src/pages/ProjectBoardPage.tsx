import { Alert, Button, Card, Empty, Skeleton, Space, Tabs, Tag, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api";
import type { Dashboard, Project, ProjectBoardTask } from "../types";

interface Props {
  project?: Project;
  onNavigate?: (page: "review" | "issues") => void;
}

type Risk = ProjectBoardTask["risk"];

const riskLabels: Record<Risk, string> = {
  todo: "待办",
  upcoming: "近期",
  overdue: "逾期",
  completed: "已完成",
};

const riskColors: Record<Risk, string> = {
  todo: "default",
  upcoming: "gold",
  overdue: "red",
  completed: "green",
};

function planText(task: ProjectBoardTask) {
  if (!task.plan || task.plan.state === "tbd") return "待确认";
  if (task.plan.state === "not_applicable") return "不适用";
  if (task.plan.start_date === task.plan.end_date) return task.plan.end_date;
  return `${task.plan.start_date} → ${task.plan.end_date}`;
}

export default function ProjectBoardPage({ project, onNavigate }: Props) {
  const [dashboard, setDashboard] = useState<Dashboard>();
  const [risk, setRisk] = useState<Risk>("todo");
  const [error, setError] = useState<string>();
  const applicableTasks = useMemo(
    () => dashboard?.tasks.filter((task) => task.plan?.state !== "not_applicable") ?? [],
    [dashboard],
  );

  useEffect(() => {
    setDashboard(undefined);
    setError(undefined);
    if (!project) return;
    api.dashboard(project.id).then(setDashboard).catch((reason: Error) => setError(reason.message));
  }, [project]);

  const tasks = useMemo(
    () => applicableTasks.filter((task) => task.risk === risk),
    [applicableTasks, risk],
  );
  const counts = useMemo(
    () =>
      Object.fromEntries(
        (["todo", "upcoming", "overdue", "completed"] as Risk[]).map((item) => [
          item,
          applicableTasks.filter((task) => task.risk === item).length,
        ]),
      ) as Record<Risk, number>,
    [applicableTasks],
  );

  if (!project) return <Empty description="先新建或选择一个项目" />;
  if (error) return <Alert type="error" message={error} showIcon />;
  if (!dashboard) return <Skeleton active />;

  return (
    <div className="page-stack">
      <div className="page-heading">
        <div>
          <Typography.Text type="secondary">{project.code}</Typography.Text>
          <Typography.Title level={2}>项目看板 · {project.name}</Typography.Title>
          <Typography.Text type="secondary">
            业务日期 {dashboard.business_date} · {dashboard.active_plan_name ?? "尚未发布计划"}
          </Typography.Text>
        </div>
        <Tag color="cyan">当前版本 v{dashboard.current_version_number}</Tag>
      </div>
      <Tabs
        activeKey={risk}
        onChange={(key) => setRisk(key as Risk)}
        items={(Object.keys(riskLabels) as Risk[]).map((item) => ({
          key: item,
          label: `${riskLabels[item]} ${counts[item]}`,
        }))}
      />
      {tasks.length === 0 ? (
        <Empty description={`暂无${riskLabels[risk]}节点`} />
      ) : (
        <div className="board-grid">
          {tasks.map((task) => (
            <Card
              key={task.code}
              title={`${task.code} · ${task.name}`}
              extra={<Tag color={riskColors[task.risk]}>{riskLabels[task.risk]}</Tag>}
            >
              <Typography.Paragraph type="secondary">计划：{planText(task)}</Typography.Paragraph>
              <Space size={[6, 6]} wrap>
                {(["R", "A", "C", "I"] as const).flatMap((role) =>
                  task.assignments[role].map((member) => (
                    <Tag key={`${role}-${member}`}>{role} {member}</Tag>
                  )),
                )}
              </Space>
            </Card>
          ))}
        </div>
      )}
      <Card title={`重难点问题 · ${dashboard.issues.length}`}>
        {dashboard.issues.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无问题" />
        ) : (
          <div className="issue-summary-list">
            {dashboard.issues.map((issue) => (
              <div key={issue.id} className="issue-summary-item">
                <div>
                  <Typography.Text strong>{issue.description}</Typography.Text>
                  <Typography.Text type="secondary"> 截止 {issue.due_date}</Typography.Text>
                </div>
                <Space size={[4, 4]} wrap>
                  <Tag color={riskColors[issue.risk]}>{riskLabels[issue.risk]}</Tag>
                  <Tag>R {issue.owner_name}</Tag>
                  {issue.accountable_names.map((member) => <Tag key={member}>A {member}</Tag>)}
                </Space>
              </div>
            ))}
          </div>
        )}
      </Card>
      <div className="board-actions">
        <Button onClick={() => onNavigate?.("review")}>项目数据与变更</Button>
        <Button type="primary" onClick={() => onNavigate?.("issues")}>管理问题</Button>
      </div>
    </div>
  );
}
