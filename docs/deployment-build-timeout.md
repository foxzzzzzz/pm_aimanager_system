# 云端构建依赖下载超时修复

日期：2026-10-22。输入证据：用户提供的`err1022-1.txt`。范围：Ubuntu生产部署失败，保留所有既有项目及通知数据。

## 1. 原因

- 日志失败点为API镜像Dockerfile最后一条`pip install --no-deps /app/apps/api`，不是数据库迁移或业务启动失败。
- 安装运行依赖的前一条命令显式使用了`PYPI_INDEX_URL`指定的清华镜像；安装本地项目的命令未传该参数。
- `pyproject.toml`声明构建依赖`setuptools>=75`。pip即使使用`--no-deps`，仍会为PEP 517隔离构建安装构建依赖。日志显示下载`setuptools-84.2.1`时访问`files.pythonhosted.org`，读取超时。
- 依据：[pip构建隔离及构建依赖说明](https://pip.pypa.io/en/stable/reference/build-system/)。`--no-deps`不等价于禁用构建隔离；本次保留隔离构建，只修正镜像配置传递。
- 用户已按先前步骤手动停止worker/beat，随后构建失败，因此通知扫描处于停止状态。先前“构建前手动停通知”的操作顺序造成了不必要的提醒中断，现由脚本调整。

## 2. 修复

1. API Dockerfile两条pip安装命令均显式使用现有`PYPI_INDEX_URL`、`PIP_DEFAULT_TIMEOUT`和重试参数；本地项目的隔离构建也使用所配镜像，不新增镜像地址硬编码，不关闭TLS验证。
2. 生产脚本先执行`compose build`，成功后才停止旧通知worker/beat，再`compose up --no-build`切换；构建失败直接退出，不停止仍在运行的服务。
3. 保留原有迁移、健康检查和运维检查。没有数据库结构、应用逻辑、项目数据或密钥修改，不清理Docker卷，也不清空构建缓存。

## 3. 验证

- 先新增回归，原实现3项失败：本地项目安装缺镜像参数、成功路径缺少构建后再停服顺序、构建失败未在切换前独立退出。
- 修复后执行新增用例及原生产部署/布局测试：9项通过。成功和失败路径均用真实Bash运行部署脚本，以受控Docker/curl函数代替真实服务；构建模拟失败返回42且没有stop/up操作。
- 真实打包验证：复制API源代码到`tmp/deploy-build-smoke/`，使用Python 3.12和显式清华镜像执行隔离`pip wheel --no-deps`。嵌套构建日志确认从清华镜像下载`setuptools-84.2.1`，最终成功生成`project_manager_api-0.5.0-py3-none-any.whl`，退出码0。
- 真实打包日志保留在忽略目录`tmp/deploy-build-smoke/build.log`，不提交到仓库。
- API全量回归184项通过（116.84秒）；ruff、mypy、Bash语法检查、默认和生产Compose配置校验通过。
- 本机Docker引擎未启动，未执行完整Linux镜像重建，未连接或改动用户云服务器；Ubuntu最终构建和健康状态需在拉取修复后确认。

## 4. Ubuntu恢复与重新部署

如果需要先恢复原版提醒，在仓库目录执行以下命令。`start`只启动既有容器，不重新构建或创建容器：

```bash
docker compose --env-file .env.production \
  -f docker-compose.yml -f docker-compose.production.yml \
  start notification-worker notification-beat
```

同步修复后，不需要再手动提前停止通知服务：

```bash
git pull --ff-only origin main
bash ./scripts/deploy-production.sh
docker compose --env-file .env.production \
  -f docker-compose.yml -f docker-compose.production.yml ps
```

无需重新运行初始化脚本，无需重导入老项目。服务器日志中已经配置清华镜像，修复会让本地包安装阶段使用同一配置；保留现有`.env.production`与所有密钥。
