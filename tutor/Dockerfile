# TUTOR Docker image - Optimized

# 构建阶段
FROM python:3.11-slim AS builder

WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装依赖到虚拟环境
RUN python -m venv /venv && \
    /venv/bin/pip install --no-cache-dir --upgrade pip && \
    /venv/bin/pip install --no-cache-dir -r requirements.txt && \
    /venv/bin/pip install --no-cache-dir "uvicorn[standard]"

# 运行阶段
FROM python:3.11-slim

WORKDIR /app

# 安装运行时依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段复制虚拟环境
COPY --from=builder /venv /venv

# 复制应用代码
COPY tutor /app/tutor

# 创建数据目录
RUN mkdir -p /app/data && \
    chmod 755 /app/data

# 环境变量
ENV PYTHONPATH="/app"
ENV TUTOR_HOME="/app/data"
ENV DATA_PATH="/app/data/tutor_runs.db"
ENV PATH="/venv/bin:$PATH"

# 暴露API端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

# 默认命令
CMD ["uvicorn", "tutor.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--timeout-keep-alive", "30"]