import { Alert, Button, Card, Descriptions, Empty, Space, Table, Tag, Typography, Upload, message } from "antd";
import { useEffect, useState } from "react";

import { api } from "../api";
import type { ImportRecord, Project } from "../types";

interface Props {
  project?: Project;
  onPublished: () => void;
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function ImportPage({ project, onPublished }: Props) {
  const [file, setFile] = useState<File>();
  const [record, setRecord] = useState<ImportRecord>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [messageApi, contextHolder] = message.useMessage();

  useEffect(() => {
    setFile(undefined);
    setRecord(undefined);
    setError(undefined);
  }, [project?.id]);

  if (!project) return <Empty description="请先选择项目" />;

  const analyze = async () => {
    if (!file) return;
    setLoading(true);
    setError(undefined);
    try {
      setRecord(await api.uploadImport(project.id, file));
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const publish = async () => {
    if (!record) return;
    setLoading(true);
    try {
      await api.publishImport(record);
      await messageApi.success("项目版本已发布");
      onPublished();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-stack">
      {contextHolder}
      <div className="page-heading">
        <div>
          <Typography.Text type="secondary">{project.code}</Typography.Text>
          <Typography.Title level={2}>Excel导入与差异确认</Typography.Title>
        </div>
      </div>
      {error && <Alert type="error" message={error} showIcon closable onClose={() => setError(undefined)} />}
      <Card>
        <Space wrap>
          <Upload
            accept=".xlsx"
            maxCount={1}
            beforeUpload={(selected) => {
              setFile(selected);
              return false;
            }}
            onRemove={() => setFile(undefined)}
          >
            <Button>选择 .xlsx 文件</Button>
          </Upload>
          <Button type="primary" disabled={!file} loading={loading} onClick={analyze}>
            解析并生成差异
          </Button>
        </Space>
      </Card>
      {record && (
        <Card
          title="导入报告"
          extra={
            <Button type="primary" loading={loading} onClick={publish}>
              确认发布
            </Button>
          }
        >
          <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 4 }}>
            <Descriptions.Item label="文件">{record.filename}</Descriptions.Item>
            <Descriptions.Item label="状态"><Tag color="green">{record.status}</Tag></Descriptions.Item>
            <Descriptions.Item label="规格">{record.report.counts.product_specs}</Descriptions.Item>
            <Descriptions.Item label="计划节点">{record.report.counts.milestones}</Descriptions.Item>
          </Descriptions>
          <Table
            className="diff-table"
            rowKey="path"
            size="small"
            pagination={{ pageSize: 10 }}
            dataSource={record.diff}
            columns={[
              { title: "字段", dataIndex: "path", width: "38%" },
              { title: "变化", dataIndex: "operation", width: 90 },
              { title: "原值", dataIndex: "before", render: displayValue },
              { title: "新值", dataIndex: "after", render: displayValue },
            ]}
          />
        </Card>
      )}
    </div>
  );
}
