# QSWeb - QuantStudio Web GUI

基于 QuantStudio 量化投资框架的 Web GUI 平台。

## 环境要求

- Python 3.10+（推荐使用 QS312 环境）
- Node.js 18+
- npm 或 yarn

## 快速开始

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

### 已实现

- [x] **数据管理**
  - [x] 因子库连接管理（创建/删除/测试连接）
  - [x] 因子树浏览（延迟加载因子表和因子列表）
  - [x] 因子数据预览（分页显示）
  - [x] 支持多种数据库后端

### 待实现

- [ ] 因子工作台（搜索、DAG 可视化、衍生因子创建）
- [ ] 回测工作台（IC 分析、分位数组合、策略回测）
- [ ] 风险管理（风险矩阵、多因子风险分解）
- [ ] 组合优化（均值方差、风险预算）
- [ ] 报告中心（报告生成和浏览）

## 支持的数据库类型

| 数据库类型 | 说明 | 配置参数 |
|-----------|------|----------|
| **HDF5DB** | HDF5 文件数据库 | `db_path`: 主目录路径 |
| **SQLDB** | 关系数据库 | `db_type`: MySQL/PostgreSQL/SQL Server/Oracle<br>`host`、`port`、`user`、`password`、`db_name` |
| **ClickHouseDB** | ClickHouse 列式数据库 | `host`、`port`、`user`、`password`、`database` |
| **MongoDB** | MongoDB 文档数据库 | `host`、`port`、`user`、`password`、`database` |
| **Neo4jDB** | Neo4j 图数据库 | `host`、`port`、`user`、`password`、`database` |

## 使用说明

### 添加因子库连接

1. 点击左侧"因子库连接"卡片中的"新建"按钮
2. 输入连接名称（如：本地 HDF5 数据库）
3. 选择数据库类型
4. 填写连接配置参数
5. 点击"确定"保存

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
├── frontend/              # 前端项目
│   ├── src/
│   │   ├── components/    # 通用组件
│   │   │   ├── Layout/    # 布局组件
│   │   │   ├── FactorTree/# 因子树组件
│   │   │   └── DataTable/ # 数据表格组件
│   │   ├── pages/         # 页面组件
│   │   │   └── DataManager/# 数据管理页面
│   │   ├── services/      # API 调用
│   │   └── styles/        # 样式
│   ├── package.json
│   └── vite.config.ts
│
├── backend/               # 后端项目
│   ├── app/
│   │   ├── api/           # API 路由
│   │   ├── models/        # 数据模型
│   │   ├── services/      # 业务服务
│   │   └── core/          # 核心配置
│   └── requirements.txt
│
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
| `/api/connections/{id}` | PUT | 更新连接 |
| `/api/connections/{id}` | DELETE | 删除连接 |
| `/api/connections/{id}/test` | POST | 测试连接 |
| `/api/factors/{conn_id}/tables` | GET | 获取因子表列表 |
| `/api/factors/{conn_id}/tables/{name}/factors` | GET | 获取因子列表 |
| `/api/factors/{conn_id}/tables/{name}/factors/{factor}/data` | GET | 获取因子数据 |

## 技术栈

- **前端**：React 18 + TypeScript + Ant Design 5 + Vite
- **后端**：FastAPI + Pydantic + Uvicorn
- **数据库**：复用 QuantStudio 已有的因子库适配器
