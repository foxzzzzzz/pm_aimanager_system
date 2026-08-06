import { Alert, Button, Space, Table, Tag, Typography } from "antd";
import { useEffect, useState } from "react";

import { api } from "../api";
import type { NotificationDelivery, Project } from "../types";

export default function NotificationsPage({ project }: { project?: Project }) {
  const [items, setItems] = useState<NotificationDelivery[]>([]);
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setItems(await api.listNotifications(project?.id));
      setError(undefined);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [project?.id]);

  const scan = async (kind: "daily" | "weekly") => {
    try {
      await api.runNotificationScan(kind);
      await load();
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Typography.Title level={2}>通知诊断</Typography.Title>
      {error && <Alert type="error" message={error} showIcon />}
      <Space>
        <Button type="primary" onClick={() => void scan("daily")}>立即执行每日扫描</Button>
        <Button onClick={() => void scan("weekly")}>立即执行周报扫描</Button>
      </Space>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={items}
        pagination={{ pageSize: 20 }}
        columns={[
          { title: "业务日期", dataIndex: "business_date" },
          { title: "事件", dataIndex: "event_type" },
          { title: "通道", dataIndex: "channel" },
          {
            title: "状态", dataIndex: "status",
            render: (value: string) => (
              <Tag color={value === "sent" ? "green" : "red"}>{value}</Tag>
            ),
          },
          { title: "尝试次数", dataIndex: "attempts" },
          { title: "错误", dataIndex: "error_message" },
          {
            title: "操作",
            render: (_value: unknown, item: NotificationDelivery) => (
              <Button
                size="small"
                disabled={item.status !== "failed" || item.channel === "in_app"}
                onClick={async () => {
                  try {
                    await api.retryNotification(item.id);
                    await load();
                  } catch (reason) {
                    setError((reason as Error).message);
                  }
                }}
              >
                重试
              </Button>
            ),
          },
        ]}
      />
    </Space>
  );
}
