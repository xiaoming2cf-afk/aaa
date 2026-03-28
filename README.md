# Economic Research Platform

这是一个面向经济研究的长期运维平台底座。

当前版本已经支持：

- 多用户网页工作台
- 私有工作区、私有知识库、私有数据资产
- 多模型 Provider
  - `openai`
  - `gemini`
  - `anthropic`
  - `openai_compatible`
- `OpenAlex` 文献检索与文献库入库
- 上传 `CSV / XLSX / JSON / PDF / TXT / MD`
- 数据清洗
- 基础 OLS 回归
- 每日经济热点简报
  - `GDELT`
  - `FRED`
- 定时任务

## 代码结构

```text
src/research_agent/
  asset_storage.py
  asgi.py
  cli.py
  config.py
  db.py
  entities.py
  platform_core.py
  platform_research.py
  provider_gateway.py
  webapp.py
  web/
```

## 本地启动

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e .
Copy-Item .env.example .env
.\.venv\Scripts\research-agent init-db
.\.venv\Scripts\research-agent serve --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

## 环境变量

`.env.example` 已包含当前所需配置。

核心字段：

```env
APP_NAME=Economic Research Platform
APP_ENV=development
APP_SECRET=development-secret-change-me
DATABASE_URL=sqlite:///./storage/platform.db
STORAGE_DIR=storage
ASSET_STORAGE_BACKEND=local
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_STORAGE_BUCKET=research-assets
RESEARCH_AGENT_REPORTS_DIR=storage/reports
PUBLIC_BASE_URL=
ENCRYPTION_KEY=
CRON_SECRET=
OPENAI_API_KEY=
RESEARCH_AGENT_MODEL=gpt-5-mini
RESEARCH_AGENT_REASONING_EFFORT=medium
SESSION_TTL_HOURS=720
GDELT_MAX_RECORDS=15
DEFAULT_FRED_SERIES=FEDFUNDS,CPIAUCSL,UNRATE,DGS10
```

说明：

- `OPENAI_API_KEY` 仅用于私有自托管时的默认值
- 公开部署建议使用用户自己的 Provider Key
- 当 `ASSET_STORAGE_BACKEND=supabase` 时，上传文件会落到 `Supabase Storage`

## CLI

```powershell
.\.venv\Scripts\research-agent doctor
.\.venv\Scripts\research-agent create-user your@email.com
.\.venv\Scripts\research-agent run-due-jobs
```

## Web API

认证：

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`

工作区：

- `GET /api/workspaces`
- `POST /api/workspaces`

连接管理：

- `GET /api/integrations`
- `POST /api/integrations`
- `POST /api/integrations/{integration_id}/test`
- `DELETE /api/integrations/{integration_id}`

知识库与数据：

- `GET /api/workspaces/{workspace_id}/knowledge`
- `POST /api/workspaces/{workspace_id}/knowledge`
- `GET /api/workspaces/{workspace_id}/assets`
- `POST /api/workspaces/{workspace_id}/assets/upload`
- `GET /api/assets/{asset_id}/download`
- `POST /api/workspaces/{workspace_id}/assets/{asset_id}/clean`
- `POST /api/workspaces/{workspace_id}/analysis/ols`

文献与简报：

- `GET /api/openalex/search`
- `GET /api/workspaces/{workspace_id}/literature`
- `POST /api/workspaces/{workspace_id}/literature/import`
- `GET /api/workspaces/{workspace_id}/briefings`
- `POST /api/workspaces/{workspace_id}/briefings/generate`

调度：

- `GET /api/workspaces/{workspace_id}/schedules`
- `POST /api/workspaces/{workspace_id}/schedules`
- `POST /api/internal/run-due-jobs`

## 免费部署路径

当前仓库已经适配一条更现实的免费部署路径：

- Web：Render Free Web Service
- 数据库：Supabase Postgres
- 文件：Supabase Storage
- 定时任务：GitHub Actions Schedule

对应文件：

- Render 蓝图：[render.yaml](D:/智能体/render.yaml)
- GitHub Actions 调度：[run-due-jobs.yml](D:/智能体/.github/workflows/run-due-jobs.yml)

### 1. Supabase

在 Supabase 创建：

- 一个项目
- 一个 Postgres 数据库
- 一个私有 Storage bucket，建议名称 `research-assets`

你需要拿到：

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- Postgres `DATABASE_URL`

注意：

- `SUPABASE_SERVICE_ROLE_KEY` 只能放服务端环境变量，不能进前端
- `research-assets` 建议保持私有 bucket

### 2. Render Free

Render 使用当前仓库的 `render.yaml`，并补这些环境变量：

- `DATABASE_URL`
- `PUBLIC_BASE_URL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

当前蓝图默认：

- `plan: free`
- `ASSET_STORAGE_BACKEND=supabase`
- 本地临时目录仅用于运行时缓存，不依赖持久盘

### 3. GitHub Actions 定时任务

仓库里已经加了调度工作流：

- 每小时的第 `7/22/37/52` 分钟触发一次
- 调用 `POST /api/internal/run-due-jobs`

需要在 GitHub 仓库的 `Actions Secrets` 里添加：

- `RESEARCH_PLATFORM_BASE_URL`
- `RESEARCH_PLATFORM_CRON_SECRET`

## 验证结果

当前本地已经验证：

- `python -m compileall src`
- `research-agent --help`
- `research-agent doctor`
- `TestClient` 烟测
  - 注册
  - 知识库写入
  - OpenAlex 检索
  - 简报生成
  - 调度创建
  - 文件上传
  - 数据清洗
  - OLS
- Playwright 浏览器验证
  - 首页可打开
  - 页面标题正确
  - 控制台错误和警告为 `0`
  - 注册流程可用

## 当前边界

- 当前没有完整账户恢复和邮件系统
- 调度任务现在主要面向经济简报
- 更重的异步任务还没有拆到独立 worker
- FRED 仍需要用户自己提供 key

## 推荐下一步

如果继续往正式产品推进，优先顺序建议是：

1. 接入数据库迁移体系
2. 补对象存储初始化和 bucket 健康检查
3. 加用户找回密码和邮箱验证
4. 增加 Background Worker
5. 增加更多经济数据源
6. 增加更完整的计量分析模块
