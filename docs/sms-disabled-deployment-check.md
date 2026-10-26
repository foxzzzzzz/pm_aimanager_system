# SMS关闭时生产部署检查误报分析

日期：2026-10-26。输入为用户提供的Ubuntu `err.txt`，对应复盘第一版发布后的部署操作。本次仅修复配置校验与部署结果判定，不启用SMS，不修改真实数据或云端环境。

## 1. 日志结论

- Docker镜像构建完成，API、Web、通知worker/beat等容器健康检查通过。
- PostgreSQL实际执行`0012_milestone_runtime_states -> 0013_retrospective_reports`迁移成功；该日志可证明此次云端迁移已执行，不能据此替代完整PostgreSQL并发或业务验收。
- 最后的`/api/v1/operations/status`返回`status=alert`，其中`notification_failures=1`、`stale_pending=0`、`unbound_recipients=4`，配置问题为“必须启用SMS”和“短信凭据不完整”。部署脚本据`alert`退出1。
- 因此本次失败发生在部署后的运营检查，不是Dockerfile打包缺文件、镜像构建失败或0013迁移失败。日志表明新容器已启动；不能把脚本非零退出理解成服务仍停留在旧版本。

## 2. 根因与修复范围

1. 现有通知逻辑、初始化脚本和环境示例均允许短信关闭，但生产配置检查无条件要求SMS开启且配置齐全。修复为关闭时不产生短信配置问题，开启时继续校验腾讯凭据、应用ID、签名和模板；其他生产约束继续有效。
2. 部署脚本将运营聚合状态与部署门禁混用。即使短信误报修正，已有通知失败和未绑定记录仍会令`status=alert`。修复为严格解析既有状态响应：真实配置问题继续阻断；仅有运营告警时输出警告和原始统计，部署可完成。

不新增API字段或配置开关，不改变运营`ok/alert`语义、告警阈值和投递记录，不隐藏或清零已有告警。独立`operational-check.ps1`仍用于严格运营巡检。关闭SMS不意味着微信或站内通知关闭；日志中的失败通知渠道和详情仍需到通知诊断核查。

`unbound_recipients=4`在现有实现中计数的是未绑定导致跳过的通知记录，不足以判断恰有4个不同人员。

## 3. 测试设计与实施

| 用例 | 操作/输入 | 预期 |
|------|-----------|------|
| SMS-01 | 关闭SMS，凭据为None、空串、占位符或完整值 | 不产生短信配置问题 |
| SMS-02 | 开启SMS，逐项缺失或使用占位符；另验完整配置 | 缺失仍失败，完整通过 |
| SMS-03 | 关闭SMS，同时缺少其他生产配置 | 其他配置约束继续失败 |
| SMS-04 | 状态有效、无配置问题，包含1条投递失败和4条未绑定记录 | 原始告警仍可见，脚本提示运营警告并完成 |
| SMS-05 | status为ok或alert，但配置问题非空 | 均退出非零，不输出部署完成 |
| SMS-06 | JSON畸形、缺字段、类型不符、未知状态或非法计数 | 拒绝异常响应，不默认为配置通过 |
| SMS-07 | 构建、启动、迁移、健康或状态请求/解析执行失败 | 原失败链有效，不输出部署完成 |
| SMS-08 | 正常ok且配置问题为空 | 原成功路径继续通过 |

先修改测试、再执行失败复现：operations与可执行Bash部署专项为19项失败、28项通过，10.71秒；失败涵盖关闭短信误报、历史告警阻断、非空配置问题和异常响应处理。随后再实施修复。

状态响应使用现有API容器中的Python解析，不新增Ubuntu宿主Python或jq依赖。验证响应结构后根据配置问题决定阻断，并保留运营告警输出；不得用无条件跳过检查修复报错。

## 4. 验收结果

| 验收 | 命令/方式 | 结果 |
|------|-----------|------|
| 条件配置、运营状态与真实Bash部署分支 | `.venv/Scripts/python.exe -m pytest apps/api/tests/test_operations.py apps/api/tests/test_deployment_build_failure.py apps/api/tests/test_production_deployment_files.py --basetemp tmp/sms-deploy-empty-values -q` | 59项通过，13.21秒；含空字符串/占位符、开启凭据、关闭保留告警及全部部署失败分支 |
| Python静态检查 | Ruff检查operations及两个改动测试文件 | 通过 |
| Bash语法 | Git Bash执行`bash -n scripts/deploy-production.sh` | 通过 |
| 独立复审 | 只读diff审查，并直接运行脚本原始解析器的字段/类型/缺失矩阵 | 未发现阻断项；54组矩阵通过 |
| Diff | `git diff --check` | 通过 |

未连接云服务器执行本次修复后的部署。Bash行为在本地通过受控Docker/curl桩验证，JSON检查运行真实Python解析器；运营状态测试使用临时SQLite，不修改真实投递记录。Ubuntu新一轮部署结果需在用户授权提交并同步修复后验证。

## 5. Ubuntu处理边界

保留现有`.env.production`和`PROJECT_MANAGER_SMS_ENABLED=false`。修复提交并同步后，沿用`bash ./scripts/deploy-production.sh`；脚本仍先构建、切换服务、执行增量迁移和健康检查，再判断生产配置与运营告警。

历史1条通知失败、4条未绑定通知记录需要继续在通知诊断处理；部署完成提示不会消除这些问题。不要通过开启未验证的短信通道来满足旧的错误检查，也不需要重新初始化环境或重导项目Excel。
