# AI项目管理系统

后台作为项目数据与规则中心，管理端负责导入和审批，小程序负责个人查看、更新与通知。

## Phase 0 快速开始

```powershell
.\scripts\bootstrap.ps1
.\scripts\check.ps1
.\scripts\dev.ps1
```

- API健康检查：`http://localhost:18000/health`
- 管理端：`http://localhost:15173`
- MinIO API/管理台：`http://localhost:19000` / `http://localhost:19001`
- PostgreSQL、Redis和MinIO由Docker Compose启动。
- 所有宿主机端口均可在 `.env` 中覆盖，默认使用项目专用端口以避免与本机现有服务冲突。
- 微信小程序使用微信开发者工具打开 `apps/mini-program`。

产品规格与实施阶段见 [docs/PRD.md](docs/PRD.md) 和 [docs/PLAN.md](docs/PLAN.md)。
