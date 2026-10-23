FROM oven/bun:1 AS build

WORKDIR /opt/app
COPY package.json bun.lock tsconfig.base.json ./
COPY packages ./packages
COPY apps ./apps
COPY config ./config
RUN bun install --frozen-lockfile
RUN bun run build-web

FROM oven/bun:1-slim AS runtime

ENV TZ=Asia/Shanghai
WORKDIR /opt/app

RUN addgroup --system agents && adduser --system --ingroup agents --home /opt/app agents
COPY --from=build /opt/app ./
RUN mkdir -p /opt/app/.agents /opt/app/logs /opt/app/cache \
    && chown -R agents:agents /opt/app

USER agents
EXPOSE 8020

CMD ["bun", "run", "packages/host/src/main.ts"]
