import { Card, ConfigProvider, Tag, Typography } from "antd";

import "./styles.css";

export function App() {
  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: "#146c5a",
          borderRadius: 10,
        },
      }}
    >
      <main className="app-shell">
        <Card className="status-card">
          <Tag color="green">Phase 0</Tag>
          <Typography.Title level={1}>AI项目管理系统</Typography.Title>
          <Typography.Paragraph className="status-copy">
            工程基线已就绪
          </Typography.Paragraph>
          <Typography.Text type="secondary">
            后续将在这里提供项目导入、差异确认、计划看板和审计功能。
          </Typography.Text>
        </Card>
      </main>
    </ConfigProvider>
  );
}
