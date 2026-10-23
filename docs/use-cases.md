# Use Cases

## Local Coding Assistant

```bash
bun run tui
```

Use the terminal app to inspect the workspace, ask questions, switch model profiles, and resume saved sessions.

## Web Workflow

```bash
bun run web
```

Open `http://localhost:8020/ui/` for browser-based interaction backed by the same TS host.

## API Integration

```bash
curl -X POST http://127.0.0.1:8020/api/v1/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"List the available model profiles"}'
```

External clients can use the HTTP API without depending on the terminal app.

## Model Profile Testing

```bash
curl -fsS http://127.0.0.1:8020/api/v1/agent/model-profiles
```

Use this endpoint to verify which profiles are configured before starting a real run.
