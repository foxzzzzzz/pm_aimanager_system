import { Empty, Skeleton, Table, Tag, Typography } from "antd";
import { useEffect, useState } from "react";

import { api } from "../api";
import type { Project, ProjectVersion } from "../types";

interface Props {
  project?: Project;
  refreshToken: number;
}

export default function HistoryPage({ project, refreshToken }: Props) {
  const [versions, setVersions] = useState<ProjectVersion[]>();

  useEffect(() => {
    if (!project) {
      setVersions(undefined);
      return;
    }
    api.listVersions(project.id).then(setVersions);
  }, [project, refreshToken]);

  if (!project) return <Empty description="请先选择项目" />;
  if (!versions) return <Skeleton active />;

  return (
    <div className="page-stack">
      <div className="page-heading">
        <Typography.Title level={2}>版本历史</Typography.Title>
        <Tag>{project.code}</Tag>
      </div>
      <Table
        rowKey="id"
        dataSource={versions}
        columns={[
          { title: "版本", dataIndex: "version_number", render: (value: number) => `v${value}` },
          { title: "文档版本", dataIndex: "document_version" },
          {
            title: "模板",
            render: (_, item: ProjectVersion) => `${item.template_id}/${item.template_version}`,
          },
          { title: "发布时间", dataIndex: "created_at", render: (value: string) => new Date(value).toLocaleString() },
        ]}
      />
    </div>
  );
}
