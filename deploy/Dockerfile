FROM node:20-alpine AS web-builder

WORKDIR /work/apps/web
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai

WORKDIR /opt/app

RUN addgroup --system agents && adduser --system --ingroup agents --home /opt/app agents

COPY pyproject.toml ./pyproject.toml
COPY src ./src
COPY config ./config
COPY main.py ./main.py

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

COPY --from=web-builder /work/apps/web/dist ./apps/web/dist

RUN mkdir -p /opt/app/logs /opt/app/cache \
    && chown -R agents:agents /opt/app

USER agents

EXPOSE 8020

CMD ["python", "-m", "agents.interfaces.server"]
