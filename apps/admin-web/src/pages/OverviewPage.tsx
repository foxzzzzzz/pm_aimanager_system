import { Alert, Card, Col, Empty, Row, Skeleton, Statistic, Table, Tag, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api";
import type { Dashboard, PlanWindow, Project } from "../types";

interface Props {
  project?: Project;
}

function scheduleText(window: PlanWindow) {
  if (window.state === "tbd") return "待确认";
  if (window.state === "not_applicable") return "不适用";
  if (window.start_date === window.end_date) return window.start_date;
  return `${window.start_date} → ${window.end_date}`;
}

export default function OverviewPage({ project }: Props) {
  const [dashboard, setDashboard] = useState<Dashboard>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    if (!project) {
      setDashboard(undefined);
      return;
    }
    api.dashboard(project.id).then(setDashboard).catch((reason: Error) => setError(reason.message));
  }, [project]);

  const milestones = useMemo(
    () =>
      Object.entries(dashboard?.milestones ?? {}).map(([name, window]) => ({
        key: name,
        name,
        schedule: scheduleText(window),
        state: window.state,
      })),
    [dashboard],
  );

  if (!project) return <Empty description="先新建或选择一个项目" />;
  if (error) return <Alert type="error" message={error} showIcon />;
  if (!dashboard) return <Skeleton active />;

  return (
    <div className="page-stack">
      <div className="page-heading">
        <div>
          <Typography.Text type="secondary">{project.code}</Typography.Text>
          <Typography.Title level={2}>{project.name}</Typography.Title>
        </div>
        <Tag color="cyan">当前版本 v{dashboard.current_version_number}</Tag>
      </div>
      <Row gutter={[16, 16]}>
        <Col xs={12} xl={6}><Card><Statistic title="产品规格" value={dashboard.counts.product_specs} /></Card></Col>
        <Col xs={12} xl={6}><Card><Statistic title="团队成员" value={dashboard.counts.members} /></Card></Col>
        <Col xs={12} xl={6}><Card><Statistic title="计划节点" value={dashboard.counts.milestones} /></Card></Col>
        <Col xs={12} xl={6}><Card><Statistic title="未关闭问题" value={dashboard.counts.issues_open} /></Card></Col>
      </Row>
      <Card title={`当前计划 · ${dashboard.active_plan_name ?? "尚未发布"}`}>
        <Table
          size="small"
          pagination={{ pageSize: 8 }}
          dataSource={milestones}
          columns={[
            { title: "节点", dataIndex: "name" },
            { title: "计划时间", dataIndex: "schedule" },
            {
              title: "状态",
              dataIndex: "state",
              render: (state: string) => (
                <Tag color={state === "scheduled" ? "green" : state === "tbd" ? "gold" : "default"}>
                  {state === "scheduled" ? "已排期" : state === "tbd" ? "待确认" : "不适用"}
                </Tag>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}
