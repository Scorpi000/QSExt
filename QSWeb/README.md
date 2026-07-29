# QSWeb - QuantStudio Web GUI

基于 QuantStudio 量化投资框架的 Web GUI 平台。

## 环境要求

- Python 3.10+（推荐使用 QS312 环境）
- Node.js 18+
- npm 或 yarn

## 快速开始

### 方式一：Docker Compose 部署（生产/演示环境）

适合小团队自部署或快速演示，一键启动前端 + 后端 + Neo4j + PostgreSQL。

**前置条件**

- Docker 20.10+
- Docker Compose 2.0+
- 主机上已存在 `~/QuantStudioConfig/` 目录（包含数据库连接配置文件）

**启动**

```bash
cd QSWeb

# 构建并启动所有服务
docker compose up -d

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f backend
```

**服务端口**

| 服务 | 端口 | 说明 |
|------|------|------|
| 前端 (Nginx) | `23000` | Web GUI 入口 |
| 后端 (FastAPI) | `28000` | REST API + WebSocket |
| Neo4j | `7474` (HTTP) / `7687` (Bolt) | 图数据库（QSRegistry 元数据） |
| PostgreSQL | `5432` | 可选业务数据库 |

启动后访问 **http://localhost:23000** 打开 QSWeb。

**管理命令**

```bash
# 停止所有服务
docker compose down

# 停止并删除数据卷（重置数据库）
docker compose down -v

# 仅重启后端
docker compose restart backend

# 查看特定服务日志
docker compose logs -f --tail=100 backend

# 进入后端容器调试
docker compose exec backend bash
```

**环境变量**

后端支持以下环境变量，可在 `docker-compose.yml` 中修改：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `QS_CONFIG_PATH` | QuantStudio 配置目录 | `/root/QuantStudioConfig` |
| `CORS_ORIGINS` | 允许跨域的前端地址 | `http://localhost:23000` |

**默认凭据**

| 服务 | 用户名 | 密码 |
|------|--------|------|
| Neo4j | `neo4j` | `neo4j123` |
| PostgreSQL | `qsweb` | `qsweb123` |

> **生产环境提醒**：请务必修改默认密码。生产部署建议使用外部数据库（已有的 Neo4j/PostgreSQL 集群），在 `docker-compose.yml` 中移除对应服务并修改后端配置。

**常见问题**

1. **后端无法访问 QuantStudio 配置**：确保主机 `~/QuantStudioConfig/` 目录存在且包含必要的配置文件（`JYDBConfig.json` 等）
2. **Neo4j 启动失败**：确保 7474/7687 端口未被占用；首次启动 APOC 插件安装可能需要几分钟
3. **前端页面空白**：检查后端是否正常 `docker compose logs backend`，确认 API 可访问
4. **WebSocket 连接失败**：检查 nginx 配置中的 WebSocket 代理设置，确认无反向代理拦截

### 方式二：使用启动脚本（开发环境）

`scripts/start.ps1` 可一键启动前后端服务，日志自动输出到 `logs/` 目录。

**前置准备**

1. 安装后端依赖：`pip install -r QSWeb/backend/requirements.txt`
2. 安装前端依赖：`cd QSWeb/frontend && npm install`
3. 修改脚本顶部配置区的 `$PythonExe` 路径，指向你的 Python 解释器

**使用方式**

```powershell
cd QSWeb

# 同时启动前后端（后端 :28000，前端 :23000）
.\scripts\start.ps1

# 仅启动后端
.\scripts\start.ps1 -NoFrontend

# 仅启动前端
.\scripts\start.ps1 -NoBackend

# 自定义端口
.\scripts\start.ps1 -BackendPort 8000 -FrontendPort 3000
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-NoFrontend` | 不启动前端 | - |
| `-NoBackend` | 不启动后端 | - |
| `-BackendPort` | 后端监听端口 | 28000 |
| `-FrontendPort` | 前端监听端口 | 23000 |

启动后日志文件位于 `QSWeb/logs/`，按 `<服务>-<时间戳>.log` 命名。

**手动配置脚本**

编辑 `scripts/start.ps1` 顶部配置区：

```powershell
# Python 解释器路径（指向 QS 环境下的 python.exe）
$PythonExe = "$env:USERPROFILE\Project\PythonEnv\QS\Scripts\python.exe"

# 日志输出目录
$LogDir = "$PSScriptRoot\..\logs"
```

### 方式二：手动分别启动

### 1. 启动后端服务

```bash
cd QSWeb/backend

# 安装依赖
pip install -r requirements.txt

# 启动服务（默认端口 28000）
uvicorn app.main:app --reload --host 0.0.0.0 --port 28000
```

启动后访问 http://localhost:28000/docs 查看 API 文档。

### 2. 启动前端服务

```bash
cd QSWeb/frontend

# 安装依赖
npm install

# 启动开发服务器（默认端口 23000）
npm run dev
```

启动后访问 http://localhost:23000 打开 Web GUI。

### 3. 局域网访问

前端和后端默认监听 `0.0.0.0`，支持局域网访问。

- 本机访问：http://localhost:23000
- 局域网访问：http://<你的IP>:23000

查看启动日志中的 Network 地址即可获取局域网访问地址。

## 功能模块

- [x] **数据管理** — 因子库连接管理、因子树浏览、数据预览、元数据编辑
- [x] **因子工作台** — 因子搜索（关键词/语义）、DAG 可视化、衍生因子创建向导
- [x] **回测工作台** — 模块化回测（IC 分析、因子分组、策略回测）、结果树展示
- [x] **风险管理** — 风险库浏览、协方差/相关系数矩阵热力图、因子风险分解
- [x] **组合优化** — 均值方差/风险预算优化、约束编辑器、权重导出
- [x] **报告中心** — 报告生成（单因子/多因子场景）、HTML/Markdown 预览、QSRegistry 注册

## 支持的数据库类型

配置参数使用 QuantStudio FactorDB 的原生参数名：

| 数据库类型 | 说明 | 配置参数 |
|-----------|------|----------|
| **HDF5DB** | HDF5 文件数据库 | `MainDir`: 主目录路径 |
| **SQLDB** | 关系数据库 | `DBType`: MySQL/PostgreSQL/SQL Server/Oracle<br>`DBName`、`IPAddr`、`Port`、`User`、`Pwd` |
| **ClickHouseDB** | ClickHouse 列式数据库 | `DBName`、`IPAddr`、`Port`、`User`、`Pwd` |
| **MongoDB** | MongoDB 文档数据库 | `DBName`、`IPAddr`、`Port`、`User`、`Pwd` |
| **Neo4jDB** | Neo4j 图数据库 | `DBName`、`IPAddr`、`Port`、`User`、`Pwd` |

## 使用说明

### 添加因子库连接

1. 点击左侧"因子库连接"卡片中的"新建"按钮
2. 输入连接名称（如：本地 HDF5 数据库）
3. 选择数据库类型
4. 填写连接配置参数（使用 QuantStudio 原生参数名）
5. 点击"确定"保存

### 配置文件

因子库连接配置存储在 **QSGraphDB（Neo4j 图数据库）** 的 `因子库` 节点中，以 FactorDB 实例自动生成的 **QSID** 作为唯一标识。

> **注意**：`~/QuantStudioConfig/QSWebConfig.json` 的 `factor_dbs` 节已废弃。如从旧版本升级，请执行下方的迁移脚本。

### 从 QSWebConfig.json 迁移连接

如果之前使用 `QSWebConfig.json` 存储连接配置，请运行迁移脚本将已有连接写入 Neo4j 图数据库：

```bash
# 预览将要迁移的连接（不实际写入）
python -m QSWeb.scripts.migrate_connections --dry-run

# 执行迁移（自动备份 QSWebConfig.json）
python -m QSWeb.scripts.migrate_connections
```

迁移脚本的行为：
- 遍历 `QSWebConfig.json` 中 `factor_dbs` 节的每条连接
- 根据 `db_type` 和 `args` 创建 FactorDB 实例并测试连接
- 将连接元数据写入 Neo4j 的 `因子库` 节点（QSID 由 FactorDB 实例自动生成）
- 迁移前自动备份 `QSWebConfig.json` 为 `QSWebConfig.json.bak.<时间戳>`
- 迁移成功后自动删除 `QSWebConfig.json` 中的 `factor_dbs` 节

**回滚**：如需回滚，恢复备份的 `QSWebConfig.json` 文件即可。代码回退到旧版本会重新从该文件读取连接。

### 浏览因子数据

1. 在左侧连接列表中点击一个连接
2. 中间区域会加载因子表树
3. 展开因子表节点，查看因子列表
4. 点击一个因子，右侧会显示数据预览

### 数据预览

- 支持日期范围筛选
- 支持设置返回行数限制
- 支持表格排序和分页

## 目录结构

```
QSWeb/
├── frontend/                  # 前端项目
│   ├── src/
│   │   ├── components/        # 通用组件
│   │   │   ├── Layout/        # 主布局（侧边栏 + 内容区）
│   │   │   ├── Loading/       # 全局 Loading + 骨架屏
│   │   │   ├── FactorTree/    # 因子树组件
│   │   │   ├── FactorSelector/# [已废弃] 因子选择器
│   │   ├── FactorPoolPanel/# 全局因子池面板
│   │   ├── FactorDiscover/# 因子发现抽屉（双源浏览）
│   │   ├── ErrorBoundary/ # 错误边界（页面崩溃恢复）
│   │   │   ├── FactorDecomposition/ # 因子风险分解组件
│   │   │   ├── MetadataEditor/# 元数据编辑器
│   │   │   ├── ModulePicker/  # 回测模块选择器
│   │   │   ├── ModuleList/    # 回测模块列表
│   │   │   ├── ResultTree/    # 回测结果树
│   │   │   ├── ResultLeaf/    # 结果叶子渲染
│   │   │   ├── RiskHeatmap/   # 风险矩阵热力图
│   │   │   └── SpecificRiskHistogram/ # 特异性风险直方图
│   │   ├── pages/             # 页面组件（懒加载）
│   │   │   ├── DataManager/   # 数据管理页面
│   │   │   ├── FactorWorkbench/# 因子工作台页面
│   │   │   ├── BacktestStudio/# 回测工作台页面
│   │   │   ├── RiskManager/   # 风险管理页面
│   │   │   ├── PortfolioOptimizer/# 组合优化页面
│   │   │   └── ReportCenter/  # 报告中心页面
│   │   ├── services/          # API 调用封装
│   │   ├── stores/            # Zustand 状态管理
│   │   ├── hooks/             # 自定义 Hooks（useTaskProgress 等）
│   │   └── styles/            # 样式
│   ├── Dockerfile             # 多阶段构建（node → nginx）
│   ├── nginx.conf             # Nginx SPA + API 代理配置
│   ├── package.json
│   └── vite.config.ts
│
├── backend/                   # 后端项目
│   ├── app/
│   │   ├── api/               # API 路由（connections/factors/registry/backtest/risk/portfolio/report）
│   │   ├── models/            # Pydantic 数据模型
│   │   ├── services/          # 业务服务（FactorService/BacktestService/QSBridge/...）
│   │   ├── tasks/             # 异步任务管理（TaskManager + WebSocket）
│   │   └── core/              # 核心配置、自定义异常
│   ├── Dockerfile             # 多阶段构建
│   └── requirements.txt
│
├── docker-compose.yml          # Docker Compose 编排文件
├── scripts/                    # 启动脚本
└── README.md
```

## 配置说明

### 后端配置

配置文件位置：`backend/.env`

```env
# QuantStudio 配置路径（存放连接配置的目录）
QS_CONFIG_PATH=~/QuantStudioConfig

# CORS 配置（允许前端访问的地址）
CORS_ORIGINS=http://localhost:23000,http://127.0.0.1:23000
```

### 前端配置

配置文件位置：`frontend/vite.config.ts`

```typescript
export default defineConfig({
  server: {
    port: 23000,           // 前端端口
    host: '0.0.0.0',       // 允许局域网访问
    proxy: {
      '/api': {
        target: 'http://localhost:28000',  // 后端地址
        changeOrigin: true,
      },
    },
  },
})
```

## 开发说明

### 添加新的数据库类型

1. 在 `backend/app/services/factor_service.py` 中添加数据库初始化逻辑
2. 在 `backend/app/services/connection_service.py` 中添加连接测试逻辑
3. 在 `frontend/src/services/connection.ts` 中添加数据库类型选项
4. 在 `frontend/src/pages/DataManager/index.tsx` 中添加配置表单

### API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/connections/` | GET | 获取所有连接 |
| `/api/connections/` | POST | 创建连接 |
| `/api/connections/{qsid}` | PUT | 更新连接 |
| `/api/connections/{qsid}` | DELETE | 删除连接（返回影响范围） |
| `/api/connections/{qsid}?confirm=true` | DELETE | 确认级联删除连接 |
| `/api/connections/{qsid}/impact` | GET | 查询删除影响范围 |
| `/api/connections/test` | POST | 测试连接（直接传参） |
| `/api/connections/health` | POST | QSGraphDB 可用性检测 |
| `/api/factors/{conn_id}/tables` | GET | 获取因子表列表 |
| `/api/factors/{conn_id}/tables/{name}/factors` | GET | 获取因子列表 |
| `/api/factors/{conn_id}/tables/{name}/factors/{factor}/data` | GET | 获取因子数据 |
| `/api/pool/factors` | POST | 添加因子到全局池 |
| `/api/pool/factors/{id}` | DELETE | 从全局池移除因子 |
| `/api/pool/save` | POST | 保存因子池到图数据库 |
| `/api/pool/load/{name}` | GET | 从图数据库加载因子池 |
| `/api/pool/list` | GET | 列出已保存的因子池 |


## 技术栈

- **前端**：React 18 + TypeScript + Ant Design 5 + Vite
- **后端**：FastAPI + Pydantic + Uvicorn
- **数据库**：复用 QuantStudio 已有的因子库适配器
