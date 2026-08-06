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

管理端支持创建项目、上传规格书、查看字段级差异、显式发布、查看看板与版本历史，以及登记问题和查看审计。管理端API写操作使用 `X-Idempotency-Key` 和当前开发身份 `X-Actor-Id`；小程序API使用微信登录后取得的Bearer token。

Docker环境通过S3兼容接口将原始规格书保存到MinIO。数据库升级后访问 `http://localhost:15173` 即可使用管理端：

```powershell
docker compose up -d
docker compose exec -T api python -m alembic -c /app/apps/api/alembic.ini upgrade head
```

Phase 2验收记录见 [docs/phase-2-verification.md](docs/phase-2-verification.md)。

## Phase 3 小程序协同闭环

小程序已提供登录/邀请绑定、我的项目、项目看板、节点完成或延期提案、问题登记和消息中心。R成员只能提交本人负责节点，A成员或项目经理审批后才会发布新的项目版本；AI只负责预填待确认表单。

本地验收默认启用开发登录。真实微信联调前需要：

1. 将 `apps/mini-program/project.config.json` 的 `appid` 替换为真实小程序AppID。
2. 在运行环境设置 `WECHAT_APP_ID`、`WECHAT_APP_SECRET`，并将 `PROJECT_MANAGER_ALLOW_DEV_WECHAT_LOGIN=false`。
3. 将 `apps/mini-program/miniprogram/config.ts` 的API地址改为已加入微信合法域名的HTTPS地址，并关闭 `useDevelopmentLogin`。

LLM通过 `LLM_API_KEY`、`llm.base_url` 和 `llm.model` 配置任意兼容Chat Completions与严格JSON Schema的服务；未配置密钥时自然语言入口使用本地规则预填，不影响结构化表单。

Phase 3验收记录见 [docs/phase-3-verification.md](docs/phase-3-verification.md)。

产品规格与实施阶段见 [docs/PRD.md](docs/PRD.md) 和 [docs/PLAN.md](docs/PLAN.md)。
