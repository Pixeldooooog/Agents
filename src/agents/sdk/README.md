# SDK Boundaries

This package separates SDK facade wiring from core behavior.

## Facade And Wiring

These files expose public entrypoints, route requests, or compose focused helpers:

- `__init__.py`
- `client.py`
- `control_handlers.py`
- `control_payloads.py`
- `event_projection.py`
- `transports.py`

Wiring files should stay thin. They should not own protocol algorithms, file mutation rules, event-shape details, or transport retry behavior.

## Contracts

These files define schemas and stable type surfaces:

- `types.py`
- `control.py`
- `transport_types.py`

Contract files should describe accepted data shapes and validation boundaries. They should not reach into platform stores or runtime state.

## Core Implementation

Domain behavior belongs in focused modules:

- Runtime event projection: `event_messages.py`, `event_tasks.py`, `event_artifacts.py`, `event_auth.py`, `event_payloads.py`, `event_fields.py`
- Session and async state: `async_messages.py`, `session_records.py`, `runtime_io.py`, `structured_io.py`
- File history and rewind behavior: `file_history.py`, `file_rewind.py`
- Remote and embedded transports: `transport_queue.py`, `transport_sse.py`, `transport_websocket.py`, `transport_hybrid.py`, `ccr.py`
- SDK MCP bridge: `mcp/control.py`
- Option/spec adaptation: `options.py`

Implementation modules should expose behavior that facade files can compose. Architecture tests enforce declared roles and line-count ceilings so SDK parity work does not collapse back into a monolithic file.
