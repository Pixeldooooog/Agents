- Think before acting. Read existing files before writing code.
- Be concise in output but thorough in reasoning.
- Prefer editing over rewriting whole files.
- Do not re-read files you have already read.
- Test your code before declaring done.
- No sycophantic openers or closing fluff.
- Keep solutions simple and direct.
- User instructions always override this file.
- Keep the whole project codebase tidy, logically layered, and structurally elegant.
- Optimize for readable, explainable code with clear names and narrow responsibilities.
- Keep individual code files reasonably small; split by feature or responsibility before files become catch-alls.
- Preserve performance discipline: avoid unnecessary work, repeated I/O, oversized in-memory scans, and avoid blocking hot paths.
- For TypeScript, use clear workspace layering instead of copying Python's deep package tree: product entrypoints belong in `apps/*`, shared runtime/domain code belongs in `packages/*`, and feature modules should be grouped by responsibility.
- Keep TS entrypoint files thin; route, terminal host, runtime, model, state, task, and tool logic should live in focused modules.
- Name nested TS files by concrete responsibility, not by vague buckets. Prefer domain/action names such as `modelProfiles.ts`, `agentRoutes.ts`, or `sessionStore.ts`; avoid generic catch-all names like `utils.ts`, `helpers.ts`, or `common.ts` unless the file is tiny and truly generic.
- Keep directory names as stable feature/domain group names and file names as the specific unit of behavior inside that domain.
- Treat variable-name semantics as part of code quality: prefer precise, intention-revealing names and avoid ambiguous abbreviations, overloaded terms, or names whose meaning only makes sense from nearby context.
- Do not add compatibility shims for abandoned Python/src-origin names; use the clean TypeScript-native contract when the project is not yet production-bound.
- Make local commits by functional phase as work progresses.
- Use git emoji in commit messages.

## Engineering quality standard

- Aim for standard, clean, readable TypeScript with explicit ownership and efficient execution. A new reader should be able to follow request → model → tool → result from the code and module map.
- Use the strict TypeScript configuration. Treat external data as `unknown`, validate it at the boundary, and narrow it before use. Do not hide invalid data behind `any`, unchecked casts, or silent empty-object fallbacks.
- Prefer direct functions and explicit data contracts. Add an abstraction only when it has a current caller and a concrete responsibility; do not add speculative frameworks, empty interfaces, unused configuration, or compatibility code without a supported consumer.
- Keep dependencies directional. Product UI and transport entrypoints may depend on core contracts; core execution must not depend on UI, HTTP routes, or terminal rendering. Avoid circular dependencies and imports through broad barrels within a package.
- Keep modules cohesive. Split by responsibility when behavior diverges, not merely to reduce line counts. Use names that explain domain meaning; comments should explain constraints and decisions rather than repeat the implementation.
- Validate configuration before I/O. Preserve distinctions among invalid configuration, unsupported capabilities, protocol errors, provider failures, timeouts, and user cancellation. Never turn malformed or incomplete provider output into apparent success.
- Make resource ownership explicit: bound buffers and loops, release stream readers and listeners, and propagate cancellation through every I/O boundary. Avoid repeated parsing, quadratic accumulation, unbounded caching, and unnecessary full-state scans in hot paths. Optimize from evidence rather than speculative complexity.
- Test observable contracts and failure paths with deterministic fixtures. Cover protocol conversion, tool-call/result correlation, malformed input, cancellation, and relevant limits. Keep fixture tests separate from live-provider acceptance; report exactly which evidence exists.
- Remove obsolete code when replacing it. Preserve unrelated work, keep changes scoped, and update the module map and relevant contracts when boundaries change.

## Agent kernel boundaries

- Model protocol adapters own provider request/response encoding and protocol capabilities (Chat Completions, Messages, Responses, and other explicitly supported protocols). They must not execute tools, decide permissions, load skills, or mutate run state.
- The runtime owns the turn loop, ordering, cancellation, and approval transitions. It consumes normalized model/tool contracts rather than provider-specific payloads.
- The tool layer owns registration, input schemas, validation, and execution contracts. Model-produced arguments are untrusted input. Built-in and external tools must pass through the same permission and approval boundary.
- Skills own discoverable instructions and contextual resources. Loading a skill does not grant permissions or create an alternative tool execution path.
- MCP owns external capability discovery, transport/session lifecycle, and translation into tool/resource/prompt contracts. MCP must not bypass runtime permissions or leak transport-specific structures into model adapters.
- Hooks observe or intervene only at documented lifecycle points with explicit input, output, ordering, timeout, and failure semantics. They must not become hidden tool execution paths or unrestricted state mutation callbacks.
- Configuration, persistence, and host wiring remain separate from protocol and domain behavior. Registration files compose implementations; they do not accumulate business logic.
- Document the complete target boundaries before sequencing implementation, and clearly distinguish implemented behavior from planned capabilities. Keep deferred native sandbox backends deferred unless the user changes that scope.

## Delivery and commits

- Before each coherent batch, inspect the current branch, dirty files, existing contracts, and relevant tests. After the batch, run checks appropriate to the changed behavior and report remaining verification gaps.
- Use a leading commit emoji with a concise, concrete message, for example `♻️ Refactor model protocol dispatch`, `🐛 Reject malformed tool arguments`, `✅ Cover streamed provider failures`, or `📝 Document kernel boundaries`.
- Commit complete, verified functional batches. Do not mix unrelated work or generated artifacts from another task into a commit. Push when authorized; never claim a push or live integration succeeded without checking its result.
