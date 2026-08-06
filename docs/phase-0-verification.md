# Phase 0 工程基线验收记录

## 验收日期

2026-08-06

## 已完成范围

- Git仓库初始化为 `main`，验收后已创建首次commit和 `v0.1.0` tag。
- FastAPI最小应用和 `/health` 接口。
- React + TypeScript + Ant Design管理端最小页面。
- 原生微信小程序TypeScript最小页面和项目配置。
- PostgreSQL、Redis、MinIO、API和管理端Docker Compose定义。
- 配置示例、Node/Python依赖锁、GitHub Actions和PowerShell统一命令。
- Lyra模板1.0脱敏Excel夹具及预期JSON。

## 自动验收结果

执行命令：

```powershell
.\scripts\check.ps1
```

| 检查项 | 结果 |
|--------|------|
| Ruff | 通过 |
| mypy strict | 通过 |
| Pytest | 6/6通过 |
| 管理端Vitest | 1/1通过 |
| 小程序Node Test | 1/1通过 |
| 管理端TypeScript | 通过 |
| 小程序TypeScript | 通过 |
| 管理端生产构建 | 通过 |
| Docker Compose配置 | 通过 |
| 五个容器健康检查 | 全部healthy |
| 管理端浏览器渲染 | 通过，无控制台错误 |

本地HTTP冒烟结果：API返回 `{"service":"project-manager-api","status":"ok"}`，管理端构建产物返回HTTP 200。

## 脱敏夹具核验

- 四个Sheet均已渲染并与原模板版式对照。
- 团队姓名替换为 `成员01` 至 `成员22`。
- 联系方式全部清空。
- ZIP/XML级手机号正则扫描通过。
- 24个里程碑和当前计划基准保留。
- RACI解析测试基准明确要求读取公式引用，不依赖缓存显示值。

## 容器级验收

本机已有服务占用Redis默认端口6379。未停止或修改该外部服务，改用Compose可配置宿主机端口完成隔离复验：

- PostgreSQL：15432
- Redis：16379
- MinIO API/Console：19000/19001
- API：18000
- 管理端：15173

验证结果：

- PostgreSQL、Redis、MinIO、API和管理端均为healthy。
- API返回 `{"service":"project-manager-api","status":"ok"}`。
- 管理端和MinIO均返回HTTP 200。
- 浏览器可见标题“AI项目管理系统”和状态“工程基线已就绪”，无控制台错误。
- 验证结束后已执行 `docker compose down`，容器和网络已移除，数据卷及构建镜像保留。

## 验收结论

Phase 0验收通过。用户已确认首次commit和 `v0.1.0` tag。
