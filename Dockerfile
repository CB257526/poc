# ==============================================================================
# 约稿费用验收工作流 - 后端 Docker 镜像
# 只包含：FastAPI + Playwright + Chrome
# 前端单独部署（nginx 托管 dist/）
# ==============================================================================

FROM python:3.12-slim

WORKDIR /app

# 设置环境变量
ENV PYTHONPATH=src \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    WEB_SCRAPER_BROWSER=chrome

# 安装系统依赖 + Google Chrome
RUN apt-get update && apt-get install -y --no-install-recommends --fix-missing \
    # 基础工具
    wget \
    gnupg \
    ca-certificates \
    curl \
    # Chrome 依赖库
    fonts-liberation \
    fonts-noto-cjk \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libgbm1 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libglib2.0-0 \
    libasound2 \
    libxshmfence1 \
    || true \
    # 清理
    && wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb || curl -L -o google-chrome-stable_current_amd64.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb || dpkg -i --force-depends ./google-chrome-stable_current_amd64.deb \
    && apt-get install -f -y \
    && rm google-chrome-stable_current_amd64.deb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 验证 Chrome 安装
RUN google-chrome --version

# 安装 uv（Python 包管理器）
RUN pip install --no-cache-dir uv

# 只装 lockfile 里的依赖，不现场 build 本项目（内网启动不能访问 PyPI）
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# 拷贝后端代码（PYTHONPATH=src，不需要再 uv run / hatchling）
COPY src/ ./src/
COPY table/ ./table/

# 运行时禁止 uv 再访问 PyPI（构建阶段不能设 UV_OFFLINE，否则 uv sync 下不了包）
ENV UV_OFFLINE=1 \
    UV_NO_SYNC=1

# 创建运行时目录
RUN mkdir -p runtime output screenshots logs

# 创建非 root 用户（Chrome 不建议 root 运行）
RUN useradd -m -u 1000 -s /bin/bash workflow && \
    chown -R workflow:workflow /app

USER workflow

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 暴露端口
EXPOSE 8000

# 启动命令（直接用构建时装好的 venv，禁止 uv run 在内网再访问 PyPI）
CMD [".venv/bin/uvicorn", "workflows.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
