FROM oven/bun:1.4.4 AS build

WORKDIR /opt/app
COPY package.json bun.lock tsconfig.base.json ./
COPY .otto ./.otto
COPY packages ./packages
COPY apps ./apps
COPY assets ./assets
COPY config ./config
RUN bun install --frozen-lockfile
RUN bun --bun run build-web

FROM oven/bun:1.4.4-slim AS runtime

ENV TZ=Asia/Shanghai
WORKDIR /opt/app

COPY --from=build --chown=bun:bun /opt/app ./
RUN mkdir -p /opt/app/.kevin /opt/app/logs /opt/app/cache \
    && chown -R bun:bun /opt/app

USER bun
EXPOSE 8020

CMD ["bun", "run", "packages/host/src/main.ts"]
