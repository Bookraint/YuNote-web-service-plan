# Hugging Face Spaces：Docker SDK（容器以 UID 1000 运行，默认对外端口 7860）
# 文档：https://huggingface.co/docs/hub/spaces-sdks-docker

FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user

USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR $HOME/app

COPY --chown=user requirements-web.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements-web.txt

COPY --chown=user . .

# Spaces 可能注入 PORT；未设置时使用 7860（与 README 中 app_port 一致）
CMD ["sh", "-c", "exec uvicorn web.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
