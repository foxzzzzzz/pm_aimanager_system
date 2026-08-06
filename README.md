# AI项目管理系统

后台作为项目数据与规则中心，管理端负责导入和审批，小程序负责个人查看、更新与通知。

## 快速开始

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

## Phase 1 固定模板解析

- 模板清单：`config/templates/lyra_project_spec-v1.0.yaml`
- 解析入口：`project_manager_api.imports.registry.ParserRegistry`
- 统一输出：`CanonicalProjectDraft` + `ImportReport`
- 数据库迁移：

```powershell
$env:PROJECT_MANAGER_DATABASE_URL="postgresql+psycopg://project_manager:change-me@localhost:15432/project_manager"
.\.venv\Scripts\python.exe -m alembic -c apps/api/alembic.ini upgrade head
```

解析器只接受 `.xlsx`。未知模板、伪装文件、缺少必要Sheet/表头、非法日期或未知RACI成员都会明确失败，不会产生正式项目版本。

## Phase 2 后台核心闭环

管理端支持创建项目、上传规格书、查看字段级差异、显式发布、查看看板与版本历史，以及登记问题和查看审计。API写操作使用 `X-Idempotency-Key`，当前开发身份使用 `X-Actor-Id`；Phase 3接入微信登录后替换为正式身份凭证。

Docker环境通过S3兼容接口将原始规格书保存到MinIO。数据库升级后访问 `http://localhost:15173` 即可使用管理端：

```powershell
docker compose up -d
docker compose exec -T api python -m alembic -c /app/apps/api/alembic.ini upgrade head
```

Phase 2验收记录见 [docs/phase-2-verification.md](docs/phase-2-verification.md)。

产品规格与实施阶段见 [docs/PRD.md](docs/PRD.md) 和 [docs/PLAN.md](docs/PLAN.md)。
