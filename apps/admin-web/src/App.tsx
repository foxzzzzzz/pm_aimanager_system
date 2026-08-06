import {
  Alert,
  Button,
  ConfigProvider,
  Form,
  Input,
  Layout,
  Menu,
  Modal,
  Select,
  Skeleton,
  Tag,
  Typography,
} from "antd";
import { lazy, Suspense, useEffect, useMemo, useState } from "react";

import { api, clearAdminToken, hasAdminToken, setAdminToken } from "./api";
import "./styles.css";
import type { Project } from "./types";

const OverviewPage = lazy(() => import("./pages/OverviewPage"));
const ImportPage = lazy(() => import("./pages/ImportPage"));
const HistoryPage = lazy(() => import("./pages/HistoryPage"));
const IssuesAuditPage = lazy(() => import("./pages/IssuesAuditPage"));
const NotificationsPage = lazy(() => import("./pages/NotificationsPage"));

type PageKey = "overview" | "imports" | "history" | "issues" | "notifications";

interface ProjectForm {
  code: string;
  name: string;
}

export function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [authenticated, setAuthenticated] = useState(hasAdminToken);
  const [adminToken, setTokenInput] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState<string>();
  const [page, setPage] = useState<PageKey>("overview");
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [refreshToken, setRefreshToken] = useState(0);
  const [form] = Form.useForm<ProjectForm>();

  useEffect(() => {
    if (!authenticated) {
      setLoading(false);
      return;
    }
    setLoading(true);
    api
      .listProjects()
      .then((items) => {
        setProjects(items);
        setSelectedProjectId((current) => current ?? items[0]?.id);
      })
      .catch((reason: Error & { status?: number }) => {
        setError(reason.message);
        if (reason.status === 401 || reason.status === 403) {
          clearAdminToken();
          setAuthenticated(false);
        }
      })
      .finally(() => setLoading(false));
  }, [authenticated]);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId),
    [projects, selectedProjectId],
  );

  const createProject = async () => {
    const values = await form.validateFields();
    try {
      const project = await api.createProject(values);
      setProjects((current) => [project, ...current.filter((item) => item.id !== project.id)]);
      setSelectedProjectId(project.id);
      setProjectModalOpen(false);
      form.resetFields();
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  const content = {
    overview: <OverviewPage project={selectedProject} />,
    imports: (
      <ImportPage
        project={selectedProject}
        onPublished={() => {
          setRefreshToken((value) => value + 1);
          setPage("overview");
        }}
      />
    ),
    history: <HistoryPage project={selectedProject} refreshToken={refreshToken} />,
    issues: <IssuesAuditPage project={selectedProject} />,
    notifications: <NotificationsPage project={selectedProject} />,
  }[page];

  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: "#0f766e",
          colorInfo: "#0f766e",
          borderRadius: 10,
          fontFamily: 'Inter, "PingFang SC", "Microsoft YaHei", sans-serif',
        },
      }}
    >
      <Layout className="app-layout">
        <Layout.Sider className="app-sider" width={248} breakpoint="lg" collapsedWidth={0}>
          <div className="brand-block">
            <div className="brand-mark">PM</div>
            <div>
              <Typography.Title level={4}>AI项目管理系统</Typography.Title>
              <Typography.Text>项目数据中心</Typography.Text>
            </div>
          </div>
          <Menu
            className="main-menu"
            theme="dark"
            mode="inline"
            selectedKeys={[page]}
            onClick={({ key }) => setPage(key as PageKey)}
            items={[
              { key: "overview", label: "项目总览" },
              { key: "imports", label: "Excel导入" },
              { key: "history", label: "版本历史" },
              { key: "issues", label: "问题与审计" },
              { key: "notifications", label: "通知诊断" },
            ]}
          />
          <div className="phase-badge"><Tag color="cyan">Phase 4</Tag><span>智能提醒与多通道通知</span></div>
        </Layout.Sider>
        <Layout>
          <Layout.Header className="top-bar">
            <Select
              aria-label="当前项目"
              className="project-select"
              placeholder="选择项目"
              loading={loading}
              value={selectedProjectId}
              onChange={setSelectedProjectId}
              options={projects.map((project) => ({
                value: project.id,
                label: `${project.code} · ${project.name}`,
              }))}
            />
            <Button type="primary" onClick={() => setProjectModalOpen(true)}>新建项目</Button>
          </Layout.Header>
          <Layout.Content className="workspace">
            {error && (
              <Alert
                className="global-alert"
                type="error"
                message={error}
                showIcon
                closable
                onClose={() => setError(undefined)}
              />
            )}
            <Suspense fallback={<Skeleton active />}>{content}</Suspense>
          </Layout.Content>
        </Layout>
      </Layout>
      <Modal
        title="管理员认证"
        open={!authenticated}
        closable={false}
        maskClosable={false}
        cancelButtonProps={{ style: { display: "none" } }}
        okText="进入系统"
        okButtonProps={{ disabled: !adminToken.trim() }}
        onOk={() => {
          setAdminToken(adminToken.trim());
          setAuthenticated(true);
        }}
      >
        <Input.Password
          aria-label="管理员访问令牌"
          value={adminToken}
          onChange={(event) => setTokenInput(event.target.value)}
          placeholder="请输入后台配置的管理员访问令牌"
        />
      </Modal>
      <Modal
        title="新建项目"
        open={projectModalOpen}
        okText="创建"
        cancelText="取消"
        onOk={createProject}
        onCancel={() => setProjectModalOpen(false)}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="code" label="项目编号" rules={[{ required: true, message: "请输入项目编号" }]}>
            <Input autoComplete="off" placeholder="例如 ZPD1322" />
          </Form.Item>
          <Form.Item name="name" label="项目名称" rules={[{ required: true, message: "请输入项目名称" }]}>
            <Input autoComplete="off" placeholder="例如 Lyra Pro" />
          </Form.Item>
        </Form>
      </Modal>
    </ConfigProvider>
  );
}
