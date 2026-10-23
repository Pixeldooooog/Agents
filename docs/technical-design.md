# Technical Design

## Design Goals

- Keep the whole implementation in TypeScript.
- Keep app entrypoints thin.
- Keep shared runtime code in `packages/core`.
- Prefer precise module and variable names over abbreviated or overloaded names.
- Keep files small enough that responsibility is obvious.

## Runtime Composition

```text
createHostServices(repoRoot)
  -> loadSettings(repoRoot)
  -> JsonStateStore
  -> AgentRuntime
  -> HTTP routes / terminal host handlers
```

`packages/host/src/services/hostServices.ts` is the composition point. It should not absorb domain behavior.

## Event Contract

Runtime events are produced in `packages/core/src/runtime/agentRuntime.ts` and projected by HTTP and terminal host layers:

```ts
type RuntimeEvent =
  | { type: "text_delta"; name: string; payload: { delta: string } }
  | { type: "model_message"; name: string; payload: { content: string } }
  | { type: "done"; name: string; payload: { status: string } };
```

Keep protocol-specific model details inside model client adapters. Keep UI projection outside `packages/core`.

## Persistence

`JsonStateStore` stores small local records and creates parent directories lazily. It is suitable for local development and smoke tests. Larger or hosted deployments can replace the store behind the same core contracts.

## Performance Notes

- Avoid repeated full-file reads when state is already available.
- Stream runtime events instead of buffering full responses where possible.
- Keep web assets prebuilt for production serving.
- Keep route handlers narrow so request parsing and runtime execution stay easy to profile.
