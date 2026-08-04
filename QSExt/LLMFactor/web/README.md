# 因子挖掘 Web 管理界面

基于 Streamlit 的可视化管理界面，用于配置、启动、监控因子挖掘过程。

## 功能

- **配置** — 设置挖掘参数（研究方向、市场、频率、模式、轮次等）
- **控制** — 启动/停止挖掘进程，查看运行状态
- **监控** — 实时查看挖掘日志和进度
- **结果** — 查看评测结果（IC 曲线、分组收益、五维雷达图）

## 安装依赖

```bash
pip install streamlit plotly streamlit-autorefresh
```

## 启动方式

```bash
# 从项目根目录启动
streamlit run QSExt/LLMFactor/web/app.py --server.port 8501

# 或者使用 Python 模块方式
python -m streamlit run QSExt/LLMFactor/web/app.py --server.port 8501
```

启动后访问 http://localhost:8501

## 目录结构

```
web/
├── app.py                # 主入口
├── pages/
│   ├── 1_配置.py         # 配置页面
│   ├── 2_控制.py         # 控制页面
│   ├── 3_监控.py         # 监控页面
│   └── 4_结果.py         # 结果页面
├── components/
│   ├── charts.py         # 图表组件（IC曲线、雷达图等）
│   ├── log_viewer.py     # 日志查看器
│   └── status_card.py    # 状态卡片
└── utils/
    ├── process.py        # 进程管理器
    └── workspace.py      # 工作目录扫描
```

## 使用流程

1. 打开 Web 界面，进入 **配置** 页面
2. 选择研究方向、市场、频率等参数，点击"保存配置"
3. 进入 **控制** 页面，点击"启动挖掘"
4. 切换到 **监控** 页面，实时查看日志和进度
5. 挖掘完成后，在 **结果** 页面查看评测结果

## 技术说明

- **Streamlit** — 纯 Python Web 框架，无需前端构建
- **plotly** — 交互式图表库
- **进程管理** — 通过 subprocess 管理挖掘子进程
- **日志流** — 使用 streamlit-autorefresh 实现自动刷新
