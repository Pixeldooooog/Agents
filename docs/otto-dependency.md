# Otto 核心依赖

Kevin 的原 `packages/core` 已迁至私有仓库
[Pixeldooooog/otto](https://github.com/Pixeldooooog/otto)。Kevin 保留
`packages/host`、`apps/*` 与产品配置，通过 `@pixeldooooog/otto-core`
加载已编译的 JavaScript 和类型声明，不再维护核心源码副本。

## 本地安装

需要 Bun 1.4.4、GitHub CLI，以及能够读取 Otto 的 GitHub 账号。

```sh
gh auth login
bun run setup
```

`setup` 先下载 `otto.lock.json` 指定的私有 Release，校验固定 SHA-256，
再执行 `bun install --frozen-lockfile`。归档只缓存在被 Git 忽略的 `.otto/`。
已有匹配归档时可离线复用，应用运行时不需要 GitHub 凭据。

## CI 与 Docker

Kevin 是公开仓库，不能提交 Otto 归档。Kevin Actions 需要配置
`OTTO_READ_TOKEN`，推荐仅授予 Otto 仓库 Contents: read 的细粒度令牌。
默认 `GITHUB_TOKEN` 无法读取另一个私有仓库。Fork PR 不会获得此 secret，
其完整构建需要由有权限的维护者在可信分支运行，不应使用 pull_request_target
执行不可信代码来绕过限制。

本地构建 Docker 前先执行 `bun run otto:download`；Docker COPY 已验证的
`.otto` 归档，不向镜像传递 GitHub token。产出的应用含编译后的核心代码，
私有仓库并不阻止应用接收者查看这些 JavaScript。

## 更新版本

在 Otto 验证并发布新 tag，审查 Release 的校验值，同时更新
`otto.lock.json` 和 host 的归档依赖路径；执行 `bun run otto:download`、
`bun install` 以更新 `bun.lock`，再运行 `bun run check`。
提交清单与 lockfile，不提交 `.otto`。Kevin 和 Bob 可以选择不同版本。

本次先完成原核心整体迁移。编程工具、Kevin 命名的默认配置仍保留在
Otto 的初版，产品工具注入和配置细分属于后续边界整理。
旧设计/验收文档中 `packages/core` 路径指迁移前 Kevin 布局，当前源码位置为
Otto 仓库的同名目录。核心测试在 Otto 执行，Kevin 验证包的产品接入。
