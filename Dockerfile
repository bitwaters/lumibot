FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LUMIBOT_CONFIG=config/chains.yaml \
    LUMIBOT_DB_PATH=/data/lumibot.db

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config

RUN pip install --no-cache-dir .

VOLUME ["/data"]

CMD ["lumibot"]
