import { describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { AgentRunService, AgentRuntime, loadSettings, specFromPayload, workspaceInstructions, JsonStateStore, resolveModelClientConfig, executeBuiltinTool, listBuiltinTools, profileDefaults } from "../src/index.js";
import { runtimeToolLoopBudget } from "../src/runtime/runtimeLimits.js";

describe("TS core", () => {
  test("loads workspace instructions unless metadata omits them", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-core-"));
    try {
      await writeFile(path.join(root, "AGENTS.md"), "Project instruction.");
      const settings = await loadSettings(root);
      const spec = specFromPayload({ message: "hello", metadata: { omit_workspace_instructions: "true" } });
      expect(await workspaceInstructions(settings.repoRoot, spec)).toBe("");
      expect(await workspaceInstructions(settings.repoRoot, { ...spec, metadata: {} })).toContain("Project instruction.");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("persists runs in a JSON state store", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-store-"));
    try {
      const file = path.join(root, "state.json");
      const store = new JsonStateStore(file);
      const run = await store.startRun(specFromPayload({ message: "hello", model: "test", api_key: "secret" }));
      await store.finishRun(run.run_id, "finished");
      const payload = JSON.parse(await readFile(file, "utf8"));
      expect(payload.runs[0].run_id).toBe(run.run_id);
      expect(payload.runs[0].spec.api_key).toBeUndefined();
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("keeps Claude agent overrides outside model providers", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-config-"));
    try {
      await writeFile(path.join(root, ".env"), [
        "ANTHROPIC_API_KEY=anthropic-key",
        "ANTHROPIC_BASE_URL=https://anthropic.example/v1",
        "ANTHROPIC_MODEL=anthropic-claude",
        "AGENT_CLAUDE_API_KEY=agent-key",
        "AGENT_CLAUDE_BASE_URL=https://agent.example/v1",
        "AGENT_CLAUDE_MODEL=agent-claude"
      ].join("\n"));
      const settings = await loadSettings(root);
      const config = resolveModelClientConfig(settings, specFromPayload({ message: "hello", protocol: "claude-messages" }));

      expect((settings.models as Record<string, unknown>).claude_agent).toBeUndefined();
      expect(settings.agent.claude).toEqual({
        apiKey: "agent-key",
        baseUrl: "https://agent.example/v1",
        model: "agent-claude"
      });
      expect(config).toMatchObject({
        protocol: "claude-messages",
        apiKey: "agent-key",
        baseUrl: "https://agent.example/v1",
        model: "agent-claude"
      });
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("loads runtime tool iteration limits from settings", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-runtime-limits-"));
    try {
      await writeFile(path.join(root, ".env"), "AGENT_MAX_TOOL_ITERATIONS=3\n");
      const settings = await loadSettings(root);
      expect(settings.agent.maxToolIterations).toBe(3);

      const zeroLimitSpec = specFromPayload({ message: "hello", runtime: { maxToolIterations: 0 } }, profileDefaults(settings));
      expect(runtimeToolLoopBudget(settings, zeroLimitSpec)).toEqual({ mode: "limited", maxIterations: 3 });

      const metadataLimitSpec = specFromPayload({ message: "hello", metadata: { maxTurns: "2" } }, profileDefaults(settings));
      expect(runtimeToolLoopBudget(settings, metadataLimitSpec)).toEqual({ mode: "limited", maxIterations: 2 });
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("executes core workspace file tools", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-tools-"));
    try {
      await executeBuiltinTool(root, "filesystem.write", { path: "notes/todo.txt", content: "alpha\nbeta" });
      const read = await executeBuiltinTool(root, "filesystem.read", { path: "notes/todo.txt" });
      expect(read.result.is_error).toBe(false);
      expect(read.result.content).toContain("alpha");

      const list = await executeBuiltinTool(root, "filesystem.list", { path: "notes" });
      expect(list.result.content).toContain("todo.txt");

      const escape = await executeBuiltinTool(root, "filesystem.read", { path: "../outside.txt" });
      expect(escape.result.is_error).toBe(true);
      expect(escape.result.content).toContain("path escapes workspace");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("executes search and patch tools", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-search-"));
    try {
      await mkdir(path.join(root, "src"), { recursive: true });
      await writeFile(path.join(root, "src", "file.ts"), "export const target = 'old';\n");

      const grep = await executeBuiltinTool(root, "search.grep", { pattern: "target", path: "src" });
      expect(grep.result.is_error).toBe(false);
      expect(grep.result.content).toContain("file.ts");

      const glob = await executeBuiltinTool(root, "search.glob", { pattern: "src/*.ts" });
      expect(glob.result.content).toContain("src/file.ts");

      const unsafePatch = await executeBuiltinTool(root, "patch.apply", { path: "src/file.ts", old_text: "old", new_text: "new" }, { fileReadState: {} });
      expect(unsafePatch.result.is_error).toBe(true);
      expect(unsafePatch.result.content).toContain("File has not been read yet");

      const fileToolContext = { fileReadState: {} };
      await executeBuiltinTool(root, "filesystem.read", { path: "src/file.ts" }, fileToolContext);
      const patch = await executeBuiltinTool(root, "patch.apply", { path: "src/file.ts", old_text: "old", new_text: "new" }, fileToolContext);
      expect(patch.result.is_error).toBe(false);
      expect(await readFile(path.join(root, "src", "file.ts"), "utf8")).toContain("'new'");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("executes process and git utility tools", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-process-"));
    try {
      await writeFile(path.join(root, "README.md"), "hello");
      const shell = await executeBuiltinTool(root, "shell.run", { command: "printf ok" });
      expect(shell.result.is_error).toBe(false);
      expect(shell.result.content).toContain("ok");

      const background = await executeBuiltinTool(root, "shell.run", { command: "printf background-ok", run_in_background: true });
      const backgroundTaskId = JSON.parse(background.result.content).backgroundTaskId;
      const output = await executeBuiltinTool(root, "shell.output", { task_id: backgroundTaskId, block: true });
      expect(JSON.parse(output.result.content).output).toContain("background-ok");

      const longBackground = await executeBuiltinTool(root, "shell.run", { command: "sleep 5", run_in_background: true, timeout_ms: 10000 });
      const longTaskId = JSON.parse(longBackground.result.content).backgroundTaskId;
      const killed = await executeBuiltinTool(root, "shell.kill", { task_id: longTaskId });
      expect(JSON.parse(killed.result.content).killed).toBe(true);

      const tests = await executeBuiltinTool(root, "test.discover", {});
      expect(tests.result.content).toContain("bun test");

      await executeBuiltinTool(root, "shell.run", { command: "git init >/dev/null 2>&1" });
      const status = await executeBuiltinTool(root, "git.status", {});
      expect(status.result.is_error).toBe(false);
      expect(status.result.content).toContain("README.md");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("exposes concrete builtin tool metadata", () => {
    const names = listBuiltinTools().map((tool) => tool.name);
    expect(names).toContain("filesystem.write");
    expect(names).toContain("search.grep");
    expect(names).toContain("patch.apply");
    expect(names).toContain("shell.run");
    expect(names).toContain("git.status");
    expect(names).toContain("task.create");
    expect(names).toContain("schedule.create");
    expect(names).toContain("memory.add");
    expect(names).toContain("todo.write");
    expect(names).toContain("plan.enter");
    expect(names).toContain("session.status");
    expect(names).toContain("permission.status");
    expect(names).toContain("hook.add");
    expect(names).toContain("structured.output");
    expect(names).toContain("config.manage");
    expect(names).toContain("user.ask");
    expect(names).toContain("command.discover");
    expect(names).toContain("prompt.templates");
    expect(names).toContain("workflow.validate");
    expect(names).toContain("web.search");
    expect(names).toContain("browser.open");
    expect(names).toContain("browser.download");
    expect(names).toContain("tool.search");
    expect(names).toContain("mcp.servers");
    expect(names).toContain("skill.discover");
    expect(names).toContain("skill.invoke");
    expect(names).toContain("plugin.discover");
    expect(names).toContain("plugin.enable");
    expect(names).toContain("notebook.edit");
    expect(names).toContain("lsp.query");
    expect(names).toContain("worktree.enter");
    expect(names).toContain("agent.profiles");
    expect(names).toContain("agent.run");
    expect(names).toContain("team.create");
    expect(names).not.toContain("Read");
    expect(names).not.toContain("TaskCreate");
    expect(names).not.toContain("WebFetch");
    expect(names).not.toContain("ToolSearch");
    expect(names).not.toContain("Agent");
  });

  test("keeps default builtin tools aligned with the canonical registry", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-default-tools-"));
    const previousBuiltinTools = process.env.AGENT_BUILTIN_TOOLS;
    try {
      const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
      await mkdir(path.join(root, "config"), { recursive: true });
      await writeFile(path.join(root, "config", "defaults.toml"), await readFile(path.join(repoRoot, "config/defaults.toml"), "utf8"));
      delete process.env.AGENT_BUILTIN_TOOLS;
      const settings = await loadSettings(root);
      const canonicalNames = listBuiltinTools().map((tool) => tool.name);

      expect(settings.agent.builtinTools).toEqual(canonicalNames);
    } finally {
      if (previousBuiltinTools === undefined) delete process.env.AGENT_BUILTIN_TOOLS;
      else process.env.AGENT_BUILTIN_TOOLS = previousBuiltinTools;
      await rm(root, { recursive: true, force: true });
    }
  });

  test("executes task state tools", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-tasks-"));
    try {
      const store = new JsonStateStore(path.join(root, "state.json"));
      const spec = specFromPayload({ message: "task", tenant_id: "tenant", user_id: "user", agent_id: "agent", workspace_id: "workspace" });

      const created = await executeBuiltinTool(root, "task.create", { title: "Review notes", input: "Review the release notes" }, { store, spec });
      expect(created.result.is_error).toBe(false);
      const createdTask = JSON.parse(created.result.content).task;

      const listed = await executeBuiltinTool(root, "task.list", {}, { store, spec });
      expect(JSON.parse(listed.result.content).tasks).toHaveLength(1);

      const updated = await executeBuiltinTool(root, "task.update", { task_id: createdTask.task_id.slice("task_".length, "task_".length + 12), status: "paused", metadata: { priority: "high" } }, { store, spec });
      const updatedTask = JSON.parse(updated.result.content).task;
      expect(updatedTask.status).toBe("paused");
      expect(updatedTask.metadata.priority).toBe("high");

      const task = await store.loadTask(createdTask.task_id);
      const step = await store.createStep(task!, "run_task_tool");
      await store.updateStep(step.step_id, "succeeded", "task output text");
      const output = await executeBuiltinTool(root, "task.output", { task_id: createdTask.task_id }, { store, spec });
      expect(JSON.parse(output.result.content).output).toContain("task output text");

      const stopped = await executeBuiltinTool(root, "task.stop", { task_id: createdTask.task_id }, { store, spec });
      expect(JSON.parse(stopped.result.content).task.status).toBe("canceled");

      const run = await executeBuiltinTool(root, "task.run", { title: "No runner", input: "Create only" }, { store, spec });
      expect(JSON.parse(run.result.content).result.runner_available).toBe(false);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("executes schedule state tools", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-schedules-"));
    try {
      const store = new JsonStateStore(path.join(root, "state.json"));
      const spec = specFromPayload({ message: "schedule", tenant_id: "tenant", user_id: "user", agent_id: "agent", workspace_id: "workspace" });

      const created = await executeBuiltinTool(root, "schedule.create", { title: "Daily check", schedule: "0 9 * * *", input: "Check status" }, { store, spec });
      expect(created.result.is_error).toBe(false);
      const createdPayload = JSON.parse(created.result.content);
      expect(createdPayload.schedule.short_id).toHaveLength(12);

      const weekly = await executeBuiltinTool(root, "schedule.create", { title: "Weekly report", schedule: "5 10 * * 1", input: "Weekly report" }, { store, spec });
      expect(JSON.parse(weekly.result.content).schedule.short_id).toHaveLength(12);

      const listed = await executeBuiltinTool(root, "schedule.list", {}, { store, spec });
      expect(JSON.parse(listed.result.content).schedules).toHaveLength(2);

      const run = await executeBuiltinTool(root, "schedule.run", { schedule_id: createdPayload.schedule.short_id }, { store, spec });
      const runPayload = JSON.parse(run.result.content);
      expect(runPayload.task.input).toBe("Check status");
      expect(runPayload.schedule.last_run_task_id).toBe(runPayload.task.task_id);

      const deleted = await executeBuiltinTool(root, "schedule.delete", { schedule_id: JSON.parse(weekly.result.content).schedule.short_id }, { store, spec });
      expect(JSON.parse(deleted.result.content).deleted).toBe(true);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("executes scoped memory state tools", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-memory-"));
    try {
      const store = new JsonStateStore(path.join(root, "state.json"));
      const spec = specFromPayload({ message: "memory", tenant_id: "tenant", user_id: "user", agent_id: "agent", workspace_id: "workspace" });

      const added = await executeBuiltinTool(root, "memory.add", { content: "Use the quiet model profile", scope: "workspace" }, { store, spec, runId: "run_memory" });
      expect(added.result.is_error).toBe(false);
      const addedMemory = JSON.parse(added.result.content).memory;
      expect(addedMemory.short_id).toHaveLength(12);

      const listed = await executeBuiltinTool(root, "memory.list", { query: "quiet" }, { store, spec });
      expect(JSON.parse(listed.result.content).memories).toHaveLength(1);

      const edited = await executeBuiltinTool(root, "memory.edit", { memory_id: addedMemory.short_id, content: "Use the fast model profile" }, { store, spec });
      expect(JSON.parse(edited.result.content).memory.content).toContain("fast");

      const forgotten = await executeBuiltinTool(root, "memory.forget", { memory_id: addedMemory.memory_id }, { store, spec });
      expect(JSON.parse(forgotten.result.content).forgotten).toBe(true);
      expect(await store.listMemories({ tenant_id: "tenant", user_id: "user", agent_id: "agent", workspace_id: "workspace" })).toHaveLength(0);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("executes todo and plan state tools", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-planning-"));
    try {
      const store = new JsonStateStore(path.join(root, "state.json"));
      const spec = specFromPayload({ message: "plan", tenant_id: "tenant", user_id: "user", agent_id: "agent", workspace_id: "workspace" });
      const context = { store, spec, runId: "run_plan" };

      const todo = await executeBuiltinTool(root, "todo.write", {
        todos: [
          { content: "Inspect code", status: "completed", activeForm: "Inspecting code" },
          { content: "Run tests", status: "in_progress", activeForm: "Running tests" }
        ]
      }, context);
      expect(todo.result.is_error).toBe(false);
      expect(JSON.parse(todo.result.content).summary.in_progress).toBe(1);

      const invalidTodo = await executeBuiltinTool(root, "todo.write", {
        todos: [
          { content: "One", status: "in_progress", activeForm: "Doing one" },
          { content: "Two", status: "in_progress", activeForm: "Doing two" }
        ]
      }, context);
      expect(invalidTodo.result.is_error).toBe(true);

      const enter = await executeBuiltinTool(root, "plan.enter", {}, context);
      expect(JSON.parse(enter.result.content).mode).toBe("plan");

      const status = await executeBuiltinTool(root, "plan.status", {}, context);
      expect(JSON.parse(status.result.content).todos).toHaveLength(2);

      const exit = await executeBuiltinTool(root, "plan.exit", { plan: "1. Implement\n2. Test", allowedPrompts: [{ tool: "shell.run", prompt: "run tests" }] }, context);
      const exitPayload = JSON.parse(exit.result.content);
      expect(exitPayload.mode).toBe("default");
      expect(exitPayload.allowedPrompts[0].tool).toBe("shell.run");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("executes session and context state tools", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-session-"));
    try {
      const store = new JsonStateStore(path.join(root, "state.json"));
      const spec = specFromPayload({ message: "session", model: "mock", tenant_id: "tenant", user_id: "user", agent_id: "agent", workspace_id: "workspace" });
      const messages = [
        { role: "system" as const, content: "System prompt" },
        { role: "user" as const, content: "First request" },
        { role: "assistant" as const, content: "First response" },
        { role: "user" as const, content: "Second request" }
      ];
      const context = { store, spec, runId: "run_session", messages, runtimeEvents: [{ type: "model_message", payload: { content: "hello" } }] };

      const status = await executeBuiltinTool(root, "session.status", {}, context);
      expect(JSON.parse(status.result.content).messages.non_system).toBe(3);

      const summary = await executeBuiltinTool(root, "session.summary", { max_messages: 2 }, context);
      expect(JSON.parse(summary.result.content).summary).toContain("Second request");

      const exported = await executeBuiltinTool(root, "session.export", { path: "exports/session.md", format: "markdown" }, context);
      const exportPayload = JSON.parse(exported.result.content);
      expect(exportPayload.path).toBe("exports/session.md");
      expect(await readFile(path.join(root, "exports/session.md"), "utf8")).toContain("Second request");

      const trace = await executeBuiltinTool(root, "context.trace", {}, context);
      expect(JSON.parse(trace.result.content).count).toBe(1);

      const rewind = await executeBuiltinTool(root, "context.rewind", { drop_last: 1 }, context);
      expect(JSON.parse(rewind.result.content).dropped_messages).toBe(1);
      expect(messages.at(-1)?.content).toBe("First response");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("executes permission and hook state tools", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-permission-hooks-"));
    try {
      const store = new JsonStateStore(path.join(root, "state.json"));
      const spec = specFromPayload({ message: "permissions", tenant_id: "tenant", user_id: "user", agent_id: "agent", workspace_id: "workspace" });
      const context = { store, spec, runId: "run_permissions" };

      const addRule = await executeBuiltinTool(root, "permission.add_rule", { behavior: "deny", tool: "shell.run" }, context);
      expect(JSON.parse(addRule.result.content).status.denied_tools).toContain("shell.run");

      const explain = await executeBuiltinTool(root, "permission.explain", { tool: "shell.run", arguments: { command: "pwd" } }, context);
      expect(JSON.parse(explain.result.content).decision.behavior).toBe("deny");

      const removeRule = await executeBuiltinTool(root, "permission.remove_rule", { tool: "shell.run" }, context);
      expect(JSON.parse(removeRule.result.content).removed[0].behavior).toBe("deny");

      const hookEvents = await executeBuiltinTool(root, "hook.events", {}, context);
      expect(JSON.parse(hookEvents.result.content).events).toContain("pre_tool_use");

      const addedHook = await executeBuiltinTool(root, "hook.add", { event: "pre_tool_use", name: "Block shell", action: "deny_tool", tool: "shell.run", content: "No shell" }, context);
      const hook = JSON.parse(addedHook.result.content).hook;
      expect(hook.short_id).toHaveLength(12);

      const hooks = await executeBuiltinTool(root, "hook.list", { event: "pre_tool_use" }, context);
      expect(JSON.parse(hooks.result.content).hooks).toHaveLength(1);

      const deleted = await executeBuiltinTool(root, "hook.delete", { hook_id: hook.short_id }, context);
      expect(JSON.parse(deleted.result.content).deleted).toBe(true);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("executes structured, config, and user interaction tools", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-ux-tools-"));
    try {
      await writeFile(path.join(root, "attachment.png"), "fake image bytes");
      const spec = specFromPayload({ message: "ux", model: "initial", tenant_id: "tenant", user_id: "user", agent_id: "agent", workspace_id: "workspace" });

      const structured = await executeBuiltinTool(root, "structured.output", { answer: "ok", count: 2 }, { spec });
      expect(JSON.parse(structured.result.content).structured_output.answer).toBe("ok");

      const getModel = await executeBuiltinTool(root, "config.manage", { setting: "model" }, { spec });
      expect(JSON.parse(getModel.result.content).value).toBe("initial");

      const setModel = await executeBuiltinTool(root, "config.manage", { setting: "model", value: "next-model" }, { spec });
      expect(JSON.parse(setModel.result.content).newValue).toBe("next-model");
      expect(spec.model).toBe("next-model");

      const ask = await executeBuiltinTool(root, "user.ask", {
        questions: [{
          question: "Which path?",
          header: "Path",
          options: [
            { label: "A", description: "Use A" },
            { label: "B", description: "Use B", preview: "B preview" }
          ]
        }],
        answers: { "Which path?": "A" }
      }, { spec });
      expect(JSON.parse(ask.result.content).answers["Which path?"]).toBe("A");

      const message = await executeBuiltinTool(root, "user.message", { message: "Done", status: "normal", attachments: ["attachment.png"] }, { spec });
      const messagePayload = JSON.parse(message.result.content);
      expect(messagePayload.attachments[0].path).toBe("attachment.png");
      expect(messagePayload.attachments[0].isImage).toBe(true);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("executes command, prompt, and workflow template tools", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-template-tools-"));
    try {
      const store = new JsonStateStore(path.join(root, "state.json"));
      const spec = specFromPayload({ message: "templates", tenant_id: "tenant", user_id: "user", agent_id: "agent", workspace_id: "workspace" });
      const context = { store, spec };

      const promptSaved = await executeBuiltinTool(root, "prompt.save", { name: "release", content: "Ship {name} with {{arguments}}", overwrite: false }, context);
      expect(JSON.parse(promptSaved.result.content).name).toBe("release");

      const promptRendered = await executeBuiltinTool(root, "prompt.render", { name: "release", arguments: { name: "Kevin" }, raw_arguments: "tests" }, context);
      expect(JSON.parse(promptRendered.result.content).prompt).toContain("Kevin with tests");

      const commandSaved = await executeBuiltinTool(root, "command.save", {
        name: "/ship",
        content: "Run release for {arguments}",
        description: "Release command",
        aliases: ["release"],
        overwrite: false
      }, context);
      expect(JSON.parse(commandSaved.result.content).name).toBe("/ship");

      const commands = await executeBuiltinTool(root, "command.discover", { query: "release" }, context);
      expect(JSON.parse(commands.result.content).commands).toHaveLength(1);

      const commandRendered = await executeBuiltinTool(root, "command.render", { name: "release", arguments: "v1" }, context);
      expect(JSON.parse(commandRendered.result.content).prompt).toContain("v1");

      const workflowNodes = [
        { node_id: "draft", kind: "task", name: "Draft release", input: "Draft notes" },
        { node_id: "approve", kind: "human_approval", name: "Approve release" }
      ];
      const workflowEdges = [{ source: "draft", target: "approve" }];
      const validated = await executeBuiltinTool(root, "workflow.validate", { nodes: workflowNodes, edges: workflowEdges }, context);
      expect(JSON.parse(validated.result.content).order).toEqual(["draft", "approve"]);

      const savedWorkflow = await executeBuiltinTool(root, "workflow.save", { name: "release-flow", nodes: workflowNodes, edges: workflowEdges, overwrite: false }, context);
      expect(JSON.parse(savedWorkflow.result.content).workflow.node_count).toBe(2);

      const ranWorkflow = await executeBuiltinTool(root, "workflow.run_saved", { name: "release-flow" }, context);
      const workflowPayload = JSON.parse(ranWorkflow.result.content);
      expect(workflowPayload.status).toBe("awaiting_approval");
      expect(workflowPayload.results[0].task.input).toBe("Draft notes");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("uses builtin tools as default enabled tools", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-default-tools-"));
    try {
      await mkdir(path.join(root, "config"), { recursive: true });
      await writeFile(path.join(root, "config", "defaults.toml"), [
        "[host]",
        "host = \"0.0.0.0\"",
        "[agent]",
        "builtin_tools = \"filesystem.read,shell.run\""
      ].join("\n"));
      const settings = await loadSettings(root);
      expect(profileDefaults(settings).enabled_tools).toEqual(["filesystem.read", "shell.run"]);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("runs an OpenAI-compatible tool call loop", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-tool-loop-"));
    const requests: any[] = [];
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        requests.push(body);
        if (requests.length === 1) {
          return Response.json({
            choices: [{
              message: {
                content: "",
                tool_calls: [{
                  id: "call_read",
                  type: "function",
                  function: { name: "filesystem__read", arguments: JSON.stringify({ path: "note.txt" }) }
                }]
              }
            }]
          });
        }
        return Response.json({ choices: [{ message: { content: `final: ${body.messages.at(-1).content}` } }] });
      }
    });
    try {
      await writeFile(path.join(root, "note.txt"), "tool loop content");
      const settings = await loadSettings(root);
      const spec = specFromPayload({
        message: "read note",
        protocol: "openai-chat",
        model: "mock",
        base_url: `http://127.0.0.1:${server.port}/v1`,
        api_key: "test",
        permission_profile: "auto",
        enabled_tools: ["filesystem.read"]
      }, profileDefaults(settings));
      const result = await new AgentRuntime({ settings }).run(spec, "read note", "run_tool_loop");
      expect(result.status).toBe("finished");
      expect(result.tool_results[0].content).toContain("tool loop content");
      expect(result.content).toContain("tool loop content");
      expect(requests[0].tools[0].function.name).toBe("filesystem__read");
      expect(requests[1].messages.at(-1).role).toBe("tool");
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("pauses tool calls when approval is required", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-tool-approval-"));
    const server = Bun.serve({
      port: 0,
      async fetch() {
        return Response.json({
          choices: [{
            message: {
              content: "",
              tool_calls: [{
                id: "call_shell",
                type: "function",
                function: { name: "shell__run", arguments: JSON.stringify({ command: "printf no" }) }
              }]
            }
          }]
        });
      }
    });
    try {
      const settings = await loadSettings(root);
      const spec = specFromPayload({
        message: "run shell",
        protocol: "openai-chat",
        model: "mock",
        base_url: `http://127.0.0.1:${server.port}/v1`,
        api_key: "test",
        permission_profile: "ask",
        enabled_tools: ["shell.run"]
      }, profileDefaults(settings));
      const result = await new AgentRuntime({ settings }).run(spec, "run shell", "run_approval");
      expect(result.status).toBe("awaiting_approval");
      expect(result.events.some((event) => event.type === "tool_approval_required")).toBe(true);
      expect(result.tool_results).toHaveLength(0);
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("continues the turn with a denied tool result", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-tool-deny-"));
    const requests: any[] = [];
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        requests.push(body);
        if ((body.messages || []).some((message: any) => message.role === "tool")) {
          return Response.json({ choices: [{ message: { content: `denied final: ${body.messages.at(-1).content}` } }] });
        }
        return Response.json({
          choices: [{
            message: {
              content: "",
              tool_calls: [{
                id: "call_shell",
                type: "function",
                function: { name: "shell__run", arguments: JSON.stringify({ command: "printf no" }) }
              }]
            }
          }]
        });
      }
    });
    try {
      const settings = await loadSettings(root);
      const spec = specFromPayload({
        message: "run shell",
        protocol: "openai-chat",
        model: "mock",
        base_url: `http://127.0.0.1:${server.port}/v1`,
        api_key: "test",
        permission_profile: "deny",
        enabled_tools: ["shell.run"]
      }, profileDefaults(settings));
      const result = await new AgentRuntime({ settings }).run(spec, "run shell", "run_denied");

      expect(result.status).toBe("finished");
      expect(result.tool_results[0]).toMatchObject({
        name: "shell.run",
        is_error: true
      });
      expect(result.tool_results[0].content).toContain("tool denied: shell.run");
      expect(result.content).toContain("tool denied: shell.run");
      expect(requests[1].messages.at(-1).role).toBe("tool");
      expect(requests[1].messages.at(-1).content).toContain("tool denied: shell.run");
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("stops tool loops at the spec runtime iteration limit", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-tool-limit-"));
    const server = Bun.serve({
      port: 0,
      async fetch() {
        return Response.json({
          choices: [{
            message: {
              content: "",
              tool_calls: [{
                id: `call_${crypto.randomUUID().replaceAll("-", "")}`,
                type: "function",
                function: { name: "filesystem__read", arguments: JSON.stringify({ path: "limit.txt" }) }
              }]
            }
          }]
        });
      }
    });
    try {
      await writeFile(path.join(root, "limit.txt"), "limit content");
      const settings = await loadSettings(root);
      const spec = specFromPayload({
        message: "loop",
        protocol: "openai-chat",
        model: "mock",
        base_url: `http://127.0.0.1:${server.port}/v1`,
        api_key: "test",
        permission_profile: "auto",
        enabled_tools: ["filesystem.read"],
        runtime: { maxToolIterations: 1 }
      }, profileDefaults(settings));
      const result = await new AgentRuntime({ settings }).run(spec, "loop", "run_tool_limit");

      expect(result.status).toBe("error");
      expect(result.tool_results).toHaveLength(1);
      expect(result.events.some((event) => event.type === "error" && event.payload?.message === "tool-call loop exceeded max iterations")).toBe(true);
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("resumes an approved tool call", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-tool-resume-"));
    const requests: any[] = [];
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        requests.push(body);
        if (requests.length === 1) {
          return Response.json({
            choices: [{
              message: {
                content: "",
                tool_calls: [{
                  id: "call_read",
                  type: "function",
                  function: { name: "filesystem__read", arguments: JSON.stringify({ path: "note.txt" }) }
                }]
              }
            }]
          });
        }
        return Response.json({ choices: [{ message: { content: `approved: ${body.messages.at(-1).content}` } }] });
      }
    });
    try {
      await writeFile(path.join(root, "note.txt"), "resume content");
      const settings = await loadSettings(root);
      const spec = specFromPayload({
        message: "read note",
        protocol: "openai-chat",
        model: "mock",
        base_url: `http://127.0.0.1:${server.port}/v1`,
        api_key: "test",
        permission_profile: "ask",
        enabled_tools: ["filesystem.read"]
      }, profileDefaults(settings));
      const runtime = new AgentRuntime({ settings });
      const paused = await runtime.run(spec, "read note", "run_resume");
      expect(paused.status).toBe("awaiting_approval");
      expect(paused.pending_approval?.tool_call.id).toBe("call_read");

      const resumed = await runtime.resumeWithApproval(spec, paused.pending_approval!, true, "run_resume");
      expect(resumed.status).toBe("finished");
      expect(resumed.tool_results[0].content).toContain("resume content");
      expect(resumed.content).toContain("resume content");
      expect(requests[1].messages.at(-1).role).toBe("tool");
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("persists approval runs through the SDK run service", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-run-service-"));
    const requests: any[] = [];
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        requests.push(body);
        if (requests.length === 1) {
          return Response.json({
            choices: [{
              message: {
                content: "",
                tool_calls: [{
                  id: "call_read",
                  type: "function",
                  function: { name: "filesystem__read", arguments: JSON.stringify({ path: "service.txt" }) }
                }]
              }
            }]
          });
        }
        return Response.json({ choices: [{ message: { content: `service final: ${body.messages.at(-1).content}` } }] });
      }
    });
    try {
      await writeFile(path.join(root, ".env"), [
        "OPENAI_API_KEY=test",
        "OPENAI_MODEL=mock",
        `OPENAI_BASE_URL=http://127.0.0.1:${server.port}/v1`
      ].join("\n"));
      await writeFile(path.join(root, "service.txt"), "service content");
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const runs = new AgentRunService({ settings, store });
      const spec = runs.specFromPayload({
        message: "read service file",
        permission_profile: "ask",
        enabled_tools: ["filesystem.read"]
      });

      const paused = await runs.runAgent(spec, "read service file");
      expect(paused.result.status).toBe("awaiting_approval");
      expect(paused.run.status).toBe("awaiting_approval");
      expect(paused.run.pending_approval?.tool_call.id).toBe("call_read");

      const resumed = await runs.resumeApproval(paused.run.run_id, true);
      expect(resumed.result.status).toBe("finished");
      expect(resumed.run.status).toBe("finished");
      expect(resumed.result.content).toContain("service content");

      const stored = await store.loadRun(paused.run.run_id);
      expect(stored?.spec.api_key).toBeUndefined();
      expect(stored?.events.map((event) => event.type)).toContain("tool_approval_required");
      expect(stored?.events.map((event) => event.type)).toContain("tool_start");
      expect(stored?.pending_approval).toBeUndefined();
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("uses the tool loop in stream mode", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-stream-tools-"));
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        if ((body.messages || []).some((message: any) => message.role === "tool")) {
          return Response.json({ choices: [{ message: { content: "stream final" } }] });
        }
        return Response.json({
          choices: [{
            message: {
              content: "",
              tool_calls: [{
                id: "call_read",
                type: "function",
                function: { name: "filesystem__read", arguments: JSON.stringify({ path: "stream.txt" }) }
              }]
            }
          }]
        });
      }
    });
    try {
      await writeFile(path.join(root, "stream.txt"), "stream tool content");
      const settings = await loadSettings(root);
      const events: string[] = [];
      const spec = specFromPayload({
        message: "stream read",
        protocol: "openai-chat",
        model: "mock",
        base_url: `http://127.0.0.1:${server.port}/v1`,
        api_key: "test",
        permission_profile: "auto",
        enabled_tools: ["filesystem.read"]
      }, profileDefaults(settings));
      const result = await new AgentRuntime({ settings, stream: true, onEvent: (event) => events.push(event.type) }).run(spec, "stream read", "run_stream_tools");
      expect(result.status).toBe("finished");
      expect(result.tool_results[0].content).toContain("stream tool content");
      expect(events).toContain("tool_start");
      expect(events).toContain("tool_result");
      expect(events).toContain("done");
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });
});
