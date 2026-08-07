# 生产运维手册

## 1. 上线门禁

上线前必须完成以下事项：

- 使用正式微信小程序`AppID`、`AppSecret`，配置已审核的订阅消息模板ID及字段，并关闭开发登录。
- 配置长度不少于32字符的`ADMIN_API_TOKEN`、`PHONE_HMAC_KEY`和有效的32字节Base64URL `PHONE_ENCRYPTION_KEY`。
- CORS仅保留实际HTTPS管理端域名，不允许`localhost`或`127.0.0.1`。
- 如启用短信，配置腾讯云SecretID/SecretKey、地域、应用ID、签名和已审核模板，并先完成测试号码验证。
- 所有生产值通过环境变量或密钥管理服务注入，不提交到Git。

使用管理员令牌查询`GET /api/v1/operations/status`。返回`ok`才满足配置和通知运行门禁；本地开发可执行：

```powershell
.\scripts\operational-check.ps1 -AllowConfigurationIssues
```

## 2. 备份与恢复

备份仅允许写入仓库内受忽略的`tmp/backups`：

```powershell
.\scripts\backup.ps1
```

每个备份包含PostgreSQL自定义格式转储、MinIO数据归档和SHA-256清单。至少每日备份，生产环境保留周期由公司数据策略确定，并将副本存放到独立受控介质。

每次上线前和每月至少一次执行一次性恢复演练：

```powershell
.\scripts\restore-test.ps1 -BackupPath .\tmp\backups\<timestamp>
```

脚本只恢复到临时数据库和临时Docker卷，校验后自动清理，不覆盖当前环境。

## 3. 日常监控与故障处理

- 每日检查API、管理端、PostgreSQL、Redis、MinIO、notification-worker和notification-beat均为运行状态。
- 告警条件包括：24小时内外部通知失败、通知滞留超过10分钟、生产配置不完整；阈值位于`config/app.example.yaml`。
- 微信失败时先确认授权次数、模板字段和微信接口响应；关键事件启用短信时会按规则降级，站内消息始终保留。
- 短信失败时保持短信开关关闭或临时关闭，核对额度、签名、模板和手机号绑定，不重复手工批量发送。
- 未绑定接收人会记录为`skipped`，项目经理应补发邀请并完成身份审核。

## 4. 回滚

1. 停止新的导入发布和人工审批，记录故障时间与受影响项目。
2. 备份当前数据库和对象存储。
3. 将应用镜像回滚至最近已验证Tag；数据库迁移仅在确认迁移脚本支持降级且已完成备份后执行。
4. 运行健康检查、权限冒烟和通知扫描；确认无重复投递后恢复业务。
5. 审计故障期间的导入、提案和通知记录，人工补偿缺失动作。

## 5. 密钥轮换

- 管理令牌和HMAC密钥轮换后，立即重启API和worker并验证管理端登录及手机号匹配。
- 手机号加密密钥采用版本封套；更换密钥前必须设计旧版本解密和重加密方案，不能直接丢弃旧密钥。
- 微信或腾讯云密钥泄露时先在平台侧吊销，再更新运行环境并检查审计日志。
