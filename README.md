# AI项目管理系统

后台作为项目数据与规则中心，管理端负责导入和审批，小程序负责个人查看、更新与通知。

## 快速开始

```powershell
.\scripts\bootstrap.ps1
.\scripts\check.ps1
.\scripts\dev.ps1
```

Docker 容器已经创建或正在运行时，可使用后台启动脚本；它会等待服务健康并执行数据库迁移：

```powershell
.\scripts\start-backend.ps1
```

Linux 环境使用对应的 Shell 脚本：

```bash
bash ./scripts/start-backend.sh
```

测试阶段如需清空当前本地 Docker Compose 项目的全部业务数据（PostgreSQL、Redis、MinIO 中的原始Excel），使用显式确认参数执行：

```powershell
.\scripts\reset-test-environment.ps1 -ConfirmTestReset
```

Linux 环境执行：

```bash
bash ./scripts/reset-test-environment.sh --confirm-test-reset
```

若服务器使用 `.env.production` 和生产 Compose 覆盖文件，但确认可清空当前验收数据，则使用更强确认参数：

```bash
bash ./scripts/reset-test-environment.sh --confirm-production-data-reset
```

该命令不可恢复。生产 Compose 模式只清 PostgreSQL、Redis 和 MinIO 项目数据，保留 `.env.production`、Caddy 配置和 TLS 证书。

- API健康检查：`http://localhost:18000/health`
- 管理端：`http://localhost:15173`
- MinIO API/管理台：`http://localhost:19000` / `http://localhost:19001`
- PostgreSQL、Redis和MinIO由Docker Compose启动。
- 所有宿主机端口均可在 `.env` 中覆盖，默认使用项目专用端口以避免与本机现有服务冲突。
- 管理端容器使用Nginx提供生产构建产物；非本机部署时通过`ADMIN_WEB_API_BASE_URL`设置浏览器可访问的API地址。
- 微信小程序使用微信开发者工具打开 `apps/mini-program`。

## 腾讯云生产部署

生产环境继续使用Docker Compose中的PostgreSQL、Redis、MinIO和通知Worker，新增Caddy作为唯一公网HTTPS入口。部署服务器只需开放`22`、`80`和`443`；其余服务端口仅绑定到服务器回环地址。

在已安装Docker Engine与Compose插件的Linux服务器上执行：

```bash
git pull
chmod +x scripts/init-production.sh scripts/deploy-production.sh
bash ./scripts/init-production.sh
bash ./scripts/deploy-production.sh
```

初始化脚本只会询问公网域名、证书邮箱和微信配置；腾讯云短信默认跳过。管理员令牌、数据库、MinIO及手机号加密密钥自动生成并保存到受忽略且权限为`600`的`.env.production`。只有选择配置短信、并完成签名、模板与小范围通道验证后，脚本才会询问短信凭证并允许启用。

部署前请确认一级域名下的`api`、`admin`子域名已经解析到服务器公网IP，并在微信公众平台将`https://api.<你的域名>`加入request合法域名。部署成功后，才将小程序的`apps/mini-program/miniprogram/config.ts`更新为真实HTTPS API、关闭`useDevelopmentLogin`，并填入正式订阅消息模板ID后上传体验版。

## Phase 1 固定模板解析

- 模板清单：`config/templates/lyra_project_spec-v1.0.yaml`
- 解析入口：`project_manager_api.imports.registry.ParserRegistry`
- 统一输出：`CanonicalProjectDraft` + `ImportReport`
- 数据库迁移：

```powershell
$env:PROJECT_MANAGER_DATABASE_URL="postgresql+psycopg://project_manager:change-me@localhost:15432/project_manager"
.\.venv\Scripts\python.exe -m alembic -c apps/api/alembic.ini upgrade head
```

解析器只接受配置允许的 `.xlsx`，并在可超时终止的隔离进程中校验ZIP条目数与解压后总大小。未知模板、伪装文件、缺少必要Sheet/表头、非法日期或未知RACI成员都会明确失败，不会产生正式项目版本。

## Phase 2 后台核心闭环

管理端支持创建项目、上传规格书、查看字段级差异、显式发布、查看看板与版本历史，以及登记问题和查看审计。管理端API使用运行时输入的Bearer token，服务端将其映射为配置的管理员身份；写操作同时使用 `X-Idempotency-Key`。小程序API使用微信登录后取得的Bearer token。

Docker环境通过S3兼容接口将原始规格书保存到MinIO。数据库升级后访问 `http://localhost:15173` 即可使用管理端：

```powershell
docker compose up -d
docker compose exec -T api python -m alembic -c /app/apps/api/alembic.ini upgrade head
```

启动前必须在 `.env` 配置 `ADMIN_API_TOKEN` 和 `PHONE_HMAC_KEY`；两者都不得提交到仓库。管理端首次打开时输入 `ADMIN_API_TOKEN`，令牌仅保存在当前浏览器会话中。

本地测试环境可直接运行 `./scripts/configure-local-secrets.ps1`，脚本会生成管理员令牌、手机号HMAC密钥和Phase 4手机号AES-GCM加密密钥；重复运行默认保留已有值，不会静默轮换密钥。

Phase 2验收记录见 [docs/phase-2-verification.md](docs/phase-2-verification.md)。

## Phase 3 小程序协同闭环

小程序已提供登录/邀请绑定、我的项目、项目看板、节点完成或延期提案、问题登记和消息中心。R成员只能提交本人负责节点，A成员或项目经理审批后才会发布新的项目版本；AI只负责预填待确认表单。

本地验收默认启用开发登录。真实微信联调前需要：

1. 将 `apps/mini-program/project.config.json` 的 `appid` 替换为真实小程序AppID。
2. 在运行环境设置 `WECHAT_APP_ID`、`WECHAT_APP_SECRET`，并将 `PROJECT_MANAGER_ALLOW_DEV_WECHAT_LOGIN=false`。
3. 将 `apps/mini-program/miniprogram/config.ts` 的API地址改为已加入微信合法域名的HTTPS地址，并关闭 `useDevelopmentLogin`。

LLM通过 `LLM_API_KEY`、`llm.base_url` 和 `llm.model` 配置任意兼容Chat Completions与严格JSON Schema的服务；未配置密钥时自然语言入口使用本地规则预填，不影响结构化表单。

Phase 3验收记录见 [docs/phase-3-verification.md](docs/phase-3-verification.md)。

Phase 3.1安全与一致性补强验收记录见 [docs/phase-3.1-verification.md](docs/phase-3.1-verification.md)。

产品规格与实施阶段见 [docs/PRD.md](docs/PRD.md) 和 [docs/PLAN.md](docs/PLAN.md)。
