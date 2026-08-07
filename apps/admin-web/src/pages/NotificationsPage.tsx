import { Alert, Button, Space, Table, Tag, Typography } from "antd";
import { useEffect, useState } from "react";

import { api } from "../api";
import type { NotificationDelivery, OperationalStatus, Project } from "../types";

export default function NotificationsPage({ project }: { project?: Project }) {
  const [items, setItems] = useState<NotificationDelivery[]>([]);
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [operations, setOperations] = useState<OperationalStatus>();

  const load = async () => {
    setLoading(true);
    try {
      const [deliveries, operationalStatus] = await Promise.all([
        api.listNotifications(project?.id),
        api.operationsStatus(),
      ]);
      setItems(deliveries);
      setOperations(operationalStatus);
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
      {operations?.status === "alert" && (
        <Alert
          type="warning"
          showIcon
          message={
            operations.configuration_issues.length > 0
              ? "生产配置待完善"
              : "通知运行异常"
          }
          description={
            operations.configuration_issues.length > 0 ? (
              <>
                <ul>
                  {operations.configuration_issues.map((issue) => <li key={issue}>{issue}</li>)}
                </ul>
                <div>
                  失败 {operations.notification_failures} 条，滞留 {operations.stale_pending} 条
                </div>
                {operations.unbound_recipients > 0 && (
                  <div>未绑定接收人 {operations.unbound_recipients} 人</div>
                )}
              </>
            ) : (
              <>
                <div>
                  失败 {operations.notification_failures} 条，滞留 {operations.stale_pending} 条
                </div>
                {operations.unbound_recipients > 0 && (
                  <div>未绑定接收人 {operations.unbound_recipients} 人</div>
                )}
              </>
            )
          }
        />
      )}
      <Space>
        <Button type="primary" onClick={() => void scan("daily")}>立即执行每日扫描</Button>
        <Button onClick={() => void scan("weekly")}>立即执行周报扫描</Button>
      </Space>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={items}
        locale={{ emptyText: "暂无通知投递记录" }}
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
