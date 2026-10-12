FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# pdfplumber 依赖 pillow；slim 镜像需要少量系统库
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --upgrade pip && python -m pip install -e .

COPY data ./data
COPY mcp ./mcp
COPY docs ./docs

RUN mkdir -p /app/data/cache /app/data/pdfs /app/out

CMD ["python", "-m", "mining_brief.cli", "brief", "生成一份关于 Pilbara 锂矿的今日简报"]
