# 项目复盘第一版验收记录

日期：2026-10-26。范围为 [专项方案](project-retrospective-improvement.md) Phase 1、PRD 8.7、PLAN 5.10。仅在本地和隔离测试数据上验收；验收完成后用户已授权提交并推送本次功能，提交状态以Git历史为准。未部署、未创建tag。

## 1. 实现范围与外部输入

- Web新增“项目复盘”入口，展示原始计划、最后批准计划、实际完成、自然日偏差、调整次数及全来源时间线。
- 原始理由与人工结论分开；原因记录分类、证据、事实确认人、意见来源和服务端代录者。证据不足可保存待确认，勾选已确认需补齐相关信息。
- 改进建议登记适用场景、具体动作、拟负责人、验收思路，可关联报告内节点/事件；第一版不增加措施状态流转和提醒。
- 独立`retrospective_reports`表保存事实、人工意见、报告修订号和确认状态，新增`0013_retrospective_reports`迁移。确认后的内容不覆盖，新增关联草稿可修订已有草稿或已确认报告。
- 创建、保存、确认使用项目范围权限和事务锁，编辑采用期望修订号；确认额外检测证据变化。SQLite测试/演示环境在本服务写路径取得写锁，PostgreSQL沿用项目行锁。
- 生成新修订时保留原始报告；基准确认重置、人工原因回到待确认。Web还保留尚未保存的意见至新草稿本地，明确提示重新核对和保存。
- 不改导入Excel的Sheet/列、现有API必填字段、小程序更新或R/A审批规则。默认分类、原计划名称使用`config/retrospectives.yaml`，配置路径可由应用配置的`retrospectives.config_path`指定。
- 首版无需新增AI账号或密钥，程序摘录生效变更的原始理由作为待核对材料，日期和生效记录由程序计算；不自动确认原因或执行资源/人事调整。

## 2. 测试先行

后端先编写`apps/api/tests/test_retrospectives.py`并执行，初始4项因接口尚未提供返回404而失败；前端先编写`ProjectRetrospectivePage.test.tsx`并执行，因页面模块不存在而失败，再实现对应功能。

专项覆盖首次多计划基准、+13/-1双偏差与两次调整、导入前未知历史、正式发布和运行覆盖重置、完成后改期、N/A/未完成/范围增删、旧审批已落地正式版本的去重、缺失生效时间、权限/代录/输入引用、幂等与修订冲突、确认快照和报告修订、隔离迁移，以及Web表单、空态、项目切换和冲突恢复。

独立审查复现的问题按“先补用例、再修复”处理：旧版本审批覆盖后续Excel计划、SQLite确认窗口并发、锁前后权限变化及缺失审批生效时间的处理。实际完成时无法可靠重建的计划应标记资料缺口，不能用最新日期消除偏差。

## 3. 自动验收结果

| 检查 | 命令 | 结果 |
|------|------|------|
| API全量回归 | `.venv/Scripts/python.exe -m pytest apps/api/tests -q --basetemp tmp/retrospective-full-pytest --tb=short` | 199项通过，163.62秒；收集后另补2项历史用例，见下一行 |
| 最终专项、配置与迁移 | `.venv/Scripts/python.exe -m pytest apps/api/tests/test_retrospectives.py apps/api/tests/test_settings.py apps/api/tests/test_database_schema.py -q --basetemp tmp/retrospective-targeted-pytest` | 22项通过，11.16秒；含复盘16项及新增的计划切换、删除后重加2项 |
| 最终API用例总数核对 | `.venv/Scripts/python.exe -m pytest apps/api/tests --collect-only -q --basetemp tmp/retrospective-collect` | 201项，2.37秒；199项全量与新增2项针对验收共同覆盖，未声称同一次运行201项 |
| Python静态检查 | `.venv/Scripts/python.exe -m ruff check apps/api/src apps/api/tests/test_retrospectives.py apps/api/tests/test_settings.py apps/api/tests/test_database_schema.py apps/api/migrations/versions/0013_retrospective_reports.py` | 通过 |
| Python类型检查 | `.venv/Scripts/python.exe -m mypy apps/api/src` | 38个源文件通过 |
| Web与小程序全量回归 | `pnpm test` | Web31项、小程序66项通过；Web9.17秒、小程序331.67毫秒 |
| 两端类型检查 | `pnpm typecheck` | 通过，3.58秒 |
| Web生产构建 | `pnpm build` | 全量联验通过；最终布局修复后再次构建通过，总8.36秒，其中Vite4.51秒 |
| 浏览器布局修复后针对验证 | Web复盘页专项、Web类型检查 | 复盘页9项通过，5.36秒；类型检查通过，浏览器热更新复验通过 |
| 增量迁移 | 专项在隔离SQLite执行upgrade、downgrade至0012、再次upgrade | 通过；既有业务数据保留，新表按预期增删 |
| 独立审核 | 独立agent复现、复核及diff审查 | 已复现阻断项修复，专项复验通过，未发现未修复的阻断项 |

首次全量命令未指定`--basetemp`，系统默认临时目录出现权限错误；修正为仓库`tmp/`路径后全量通过。此环境错误未通过修改业务代码或跳过用例掩盖。

主要日志保存在被Git忽略的`tmp/retrospective-full-pytest.log`、`tmp/retrospective-pnpm-test.log`、`tmp/retrospective-pnpm-typecheck.log`、`tmp/retrospective-pnpm-build-final.log`。

## 4. 现有真实模板对账范围

现有`source/`仅有V1.4立项规格书模板，已用现有解析器只读验证：结构版本1.1，28节点，3行计划；实际完成均为待定。三行计划的“有日期/待定/不适用”分别为16/1/11、17/0/11、14/3/11。

该资料可以验证模板兼容、原始与活动计划区分、节点身份、N/A和缺失值；不能验证真实完结项目的延期天数、完整审批历史或原因真实性。文件包含的其他变更工作表未纳入既有解析模型，本轮不扩展Excel解析范围，也不将其当作已采集审批证据。

已记录原文件读取前后哈希一致；在仓库`tmp/`内的隔离SQLite生成报告，与解析结果逐节点核对原始计划、活动计划和实际完成，28节点差异为0。脚本为`tmp/retrospective_source_reconciliation.py`，结果为`tmp/retrospective-source-reconciliation.json`；测试数据库随隔离上下文释放，未连接业务数据库。

## 5. 浏览器联合验收

使用仅本机可访问的Vite页面和临时SQLite/API实例，不读取真实业务数据库，不发送微信或短信。使用明确标记的模拟项目验证生成草稿、原因与建议保存、确认只读及新建修订；验收截图如有生成仅展示模拟数据。

已通过真实浏览器操作验证：从“项目复盘”入口生成报告1；核对+13/-1偏差及两次生效变更；填写基准依据、原因分类/证据/确认人/意见来源和措施四项；保存后确认，所有人工字段只读；创建报告2修订，意见保留但基准与原因确认重置，保存后切回报告1仍保持原确认状态与原内容。

1253px视口初验发现Table撑大页面造成整页横向溢出，已仅对新增复盘页约束网格和卡片宽度、允许长证据换行，复验表格内部横滚且页面不再整体溢出。截图见`tmp/retrospective-confirmed-overview.png`和`tmp/retrospective-report-confirmed.png`，均为模拟资料。

验收结束已关闭浏览器临时页、停止本次创建的API与Vite服务，确认18910、15174不再监听，未停止其他服务。

## 6. 后续业务核验与部署边界

用户已明确本轮暂时没有已完结项目，先完成实现与自动验收。真实项目核验单独列待办：提供具备原始承诺、变更审批、实际完成信息的项目后，由项目经理和相关主R核对报告及改进措施可执行性；不能将模拟用例通过当作真实原因已验证。

Phase 2措施闭环与Phase 3新项目检查点仍待开始，本轮不实施。部署前按现有流程备份并执行数据库增量迁移，同时发布含新增配置的后端和Web；本记录不表示生产迁移已执行。

Docker CLI存在，但Docker daemon未运行；本轮仅只读检查状态，未自动启动Docker，未执行真实PostgreSQL迁移、并发或部署验收。该部分单列待办，不能将SQLite测试代替PostgreSQL验证。
