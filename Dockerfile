# Laya HTTP server (laya.serve wire protocol). The model is NOT in the image: mount a
# checkpoint directory (model.safetensors + rl_agent_config.json + encoder/ + tokenizer/)
# read-only on /models/laya. See docker-compose.yml / README.md.
#   docker build -t laya-server .
FROM python:3.12-slim

# CPU torch by default (small image). For an NVIDIA GPU host:
#   --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu126
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG LAYA_VERSION=0.4.24

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HOME=/tmp/hf \
    LAYA_MODEL_DIR=/models/laya \
    LAYA_MODEL_NAME=laya-local \
    LAYA_HOST=0.0.0.0 \
    LAYA_PORT=8000

RUN pip install --index-url "${TORCH_INDEX_URL}" torch \
 && pip install "laya[serve]==${LAYA_VERSION}"

RUN useradd --create-home --uid 10001 laya \
 && mkdir -p /models/laya
WORKDIR /app
COPY --chown=laya:laya app.py /app/app.py

USER laya
EXPOSE 8000

# /health answers {"status":"ok"} without auth even when LAYA_API_KEY is set.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('LAYA_PORT','8000'),timeout=4)" || exit 1

CMD ["python", "/app/app.py"]
