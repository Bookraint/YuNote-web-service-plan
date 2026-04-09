# Hugging Face Spaces：Docker SDK（容器以 UID 1000 运行，默认对外端口 7860）
# 文档：https://huggingface.co/docs/hub/spaces-sdks-docker
# 依赖安装与本地一致：`uv lock` / `uv sync`（见 pyproject.toml + uv.lock）

FROM python:3.12-slim-bookworm

# 与仓库根目录 `uv` 版本解耦，由官方镜像提供二进制
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user

USER user
ENV HOME=/home/user \
    PATH=/home/user/app/.venv/bin:$PATH \
    UV_LINK_MODE=copy
WORKDIR $HOME/app

# 依赖层：仅 pyproject.toml + uv.lock，便于构建缓存
COPY --chown=user pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY --chown=user . .

# Spaces 可能注入 PORT；未设置时使用 7860（与 README 中 app_port 一致）
CMD ["sh", "-c", "exec uvicorn web.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
