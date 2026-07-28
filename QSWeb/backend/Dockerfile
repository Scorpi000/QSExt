# ─── 构建阶段 ───────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 创建虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 安装 Python 依赖到虚拟环境
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── 运行阶段 ───────────────────────────────────────
FROM python:3.12-slim AS runner

WORKDIR /app

# 从 builder 复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 复制应用代码
COPY . .

# 创建非 root 用户
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# 暴露端口
EXPOSE 28000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:28000/health')" || exit 1

# 启动服务
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "28000"]
