# Phase 1 领域模型与固定模板解析验收记录

## 验收日期

2026-08-06

## 已完成范围

- CanonicalProjectDraft及规格、成员、计划、里程碑、RACI统一领域模型。
- `lyra_project_spec/1.0` 外部YAML模板清单和ParserRegistry。
- LyraTemplateV1Parser固定模板解析器。
- `.xlsx`文件类型、模板指纹、必要Sheet/表头、节点、日期和RACI语义校验。
- 空白（TBD）、`N/A`（NOT_APPLICABLE）、单日及日期区间的明确建模。
- 直接解析RACI公式引用，不依赖Excel缓存显示值。
- 字段级语义Diff和结构化ImportReport。
- Project、ProjectVersion、ImportRecord SQLAlchemy模型及首次Alembic迁移。

## XLSX-01至XLSX-08结果

| 用例 | 验收结果 |
|------|----------|
| XLSX-01 基准模板 | 通过；模板、项目、规格、成员和节点均匹配人工基准 |
| XLSX-02 计划版本 | 通过；识别3个完整计划快照，最后版本为候选当前计划 |
| XLSX-03 空白与N/A | 通过；分别映射为TBD与NOT_APPLICABLE |
| XLSX-04 单日与区间 | 通过；日期边界与人工基准一致 |
| XLSX-05 RACI公式 | 通过；24个节点均解析R/A/C/I和输出物 |
| XLSX-06 缺少结构 | 通过；错误包含具体Sheet或单元格位置 |
| XLSX-07 xls/伪装文件 | 通过；在解析前拒绝 |
| XLSX-08 未知模板 | 通过；返回支持的 `lyra_project_spec/1.0` |

## 基准解析报告

```json
{
  "template": "lyra_project_spec/1.0",
  "counts": {
    "product_specs": 70,
    "members": 22,
    "milestones": 24,
    "plan_versions": 3
  },
  "warnings": [
    "candidate current plan contains 3 TBD milestone(s)"
  ],
  "errors": []
}
```

当前计划中的3个TBD节点为 `DVT-SMT贴片`、`DVT装机`、`DVT可靠性测试`，与人工基准一致，不是解析错误。

## 自动化与数据库验收

执行 `./scripts/check.ps1`：

| 检查项 | 结果 |
|--------|------|
| Ruff | 通过 |
| mypy strict | 通过 |
| 后端Pytest | 27/27通过，其中Phase 1新增20个用例 |
| 管理端Vitest | 1/1通过 |
| 小程序Node Test | 1/1通过 |
| 管理端/小程序TypeScript | 通过 |
| 管理端生产构建 | 通过；既有565KB拆包提示保留为P2待办 |
| Docker Compose配置 | 通过 |

数据库验证：

- SQLite临时库完成 `upgrade head` 和 `downgrade base` 往返验证。
- PostgreSQL 17实际完成 `0001_phase1` 升级。
- PostgreSQL存在 `projects`、`project_versions`、`import_records` 和 `alembic_version`。
- API容器健康，容器内可加载模板清单、openpyxl 3.1.5和SQLAlchemy 2.0.51。

## 验收结论

Phase 1验收通过。无效文件在解析阶段明确失败，当前不存在绕过解析器写入正式ProjectVersion的路径。用户已确认本次提交和 `v0.2.0` tag。
