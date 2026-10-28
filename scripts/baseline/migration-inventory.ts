import { execFileSync } from "node:child_process";
import { readFile, writeFile, access } from "node:fs/promises";
import { listBuiltinTools } from "@pixeldooooog/otto-core";

const git = (...args: string[]) => execFileSync("git", args, { encoding: "utf8", maxBuffer: 8 * 1024 * 1024 }).trim();
const baseline = git("rev-parse", "f3bc0bb^");
const paths = git("ls-tree", "-r", "--name-only", baseline, "src/agents").split("\n").filter(p => p.endsWith(".py"));
// Domain mapping is explicit and conservative: file coverage is not semantic parity.
const mappings: [string, string[], string][] = [
  ["entrypoints", ["packages/host/src/main.ts", "apps/terminal/src/main.tsx"], "CLI/doctor behavior parity pending"],
  ["interfaces/bridge", ["packages/host/src/terminal", "apps/terminal/src"], "TS bridge replaces Python fallback; slash/interactive parity pending"],
  ["interfaces/server", ["packages/host/src/api", "packages/host/src/http"], "HTTP route surface exists; payload, errors, concurrency and SSE parity pending"],
  ["kernel/assembly", ["packages/core/src/runtime", "packages/core/src/config"], "Composition exists; sandbox/checkpoint injection not equivalent"],
  ["kernel/capabilities/sandbox", ["packages/core/src/execution"], "GAP: bounded host execution only; legacy Docker/recording sandbox not migrated"],
  ["kernel/capabilities/tools", ["packages/core/src/tools", "packages/core/src/workspace"], "Registered-name comparison below; schemas, aliases and side effects require separate verification"],
  ["kernel/capabilities/memory", ["packages/core/src/memory"], "JSON memory is not target Markdown/index architecture"],
  ["kernel/capabilities/web", ["packages/core/src/web"], "Provider/policy implementations exist; real-service coverage pending"],
  ["kernel/capabilities/skills", ["packages/core/src/extensions"], "Discovery exists; execution/security semantics pending"],
  ["kernel/capabilities", ["packages/core/src/extensions", "packages/core/src/workspace"], "IDE/skill environment compatibility requires focused audit"],
  ["kernel/config", ["packages/core/src/config"], "Settings replaced; legacy environment names not all supported"],
  ["kernel/context", ["packages/core/src/session", "packages/core/src/sdk/sdkSessionCompaction.ts"], "Context compiler/source budget parity pending"],
  ["kernel/governance", ["packages/core/src/permissions", "packages/core/src/contracts/authority.ts"], "GAP: legacy audit, credential/sandbox governance and target grants not integrated"],
  ["kernel/hooks", ["packages/core/src/hooks"], "Records/tools exist; actual hook lifecycle parity pending"],
  ["kernel/mcp", ["packages/core/src/mcp", "packages/core/src/sdk/sdkMcpControlHandlers.ts"], "Injected provider/local protocol tests; real MCP auth/lifecycle pending"],
  ["kernel/models", ["packages/core/src/models"], "Protocol implementations exist; real providers pending"],
  ["kernel/orchestration", ["packages/core/src/collaboration"], "Compatibility retained; multi-agent product is outside baseline scope"],
  ["kernel/persistence", ["packages/core/src/store", "packages/core/src/ports"], "GAP: JSON has no transactional SQLite/ledger/outbox guarantee"],
  ["kernel/runtime", ["packages/core/src/runtime"], "Single-turn runtime exists; target durable state machine not integrated"],
  ["kernel/specs", ["packages/core/src/types/agentTypes.ts"], "Spec conversion exists; field-by-field equivalence pending"],
  ["kernel/state", ["packages/core/src/store"], "GAP: artifact/checkpoint/audit/trace domains not fully represented"],
  ["kernel/tasks", ["packages/core/src/tasks"], "Single-process task service; durable ownership/cancel/recovery pending"],
  ["kernel/workflows", ["packages/core/src/workflow"], "Workflow compatibility retained; durable steps not proven"],
  ["kernel/memory_paths.py", ["packages/core/src/memory"], "Target Markdown file layout pending"],
  ["kernel/schedules.py", ["packages/core/src/schedules"], "Records/manual entry exist; supervised scheduler pending"],
  ["kernel/schema.py", ["packages/core/src/types", "packages/core/src/contracts"], "Legacy and v1 target contracts coexist; wire migration pending"],
  ["kernel/session_state.py", ["packages/core/src/session"], "Scope and restoration semantics pending"],
  ["kernel/teams.py", ["packages/core/src/collaboration"], "Compatibility retained; not personal-agent baseline acceptance"],
  ["platform/sessions", ["packages/core/src/runtime/agentRunService.ts", "packages/core/src/sdk/sdkSession.ts"], "GAP: persistent trace/sandbox/session lifecycle not equivalent"],
  ["platform", ["packages/core/src/config", "packages/core/src/store", "packages/host/src/services"], "GAP: durable persistence factory not migrated"],
  ["sdk", ["packages/core/src/sdk"], "SDK tests cover selected behavior; complete alias/wire/error matrix pending"]
];
const groups = mappings.map(([legacyPrefix, targets, gap]) => ({ legacyPrefix, targets, gap, legacyFiles: [] as string[] }));
const packageMarkers: string[] = [];
for (const file of paths) {
  const relative = file.slice("src/agents/".length);
  if (["__init__.py", "interfaces/__init__.py", "kernel/__init__.py"].includes(relative)) { packageMarkers.push(file); continue; }
  const group = groups.find(g => relative === g.legacyPrefix || relative.startsWith(`${g.legacyPrefix}/`));
  if (!group) throw Error(`Unmapped legacy file: ${file}`);
  group.legacyFiles.push(file);
}
for (const group of groups) for (const target of group.targets) {
  if (target.startsWith("packages/core/")) {
    const ottoSourceRoot = process.env.OTTO_SOURCE_ROOT;
    if (!ottoSourceRoot) throw new Error("Historical core inventory requires OTTO_SOURCE_ROOT pointing to the Otto checkout; application builds only need the release package.");
    await access(`${ottoSourceRoot}/${target}`);
    continue;
  }
  await access(target);
}
const legacyNames = new Map<string, string[]>();
for (const file of paths.filter(p => p.includes("/tools/builtin/") && p.endsWith("registration.py"))) {
  const source = git("show", `${baseline}:${file}`);
  for (const match of source.matchAll(/_register_builtin_tool\(\s*registry,\s*name\s*=\s*["']([^"']+)["']/g)) {
    const refs = legacyNames.get(match[1]) || [];
    refs.push(file); legacyNames.set(match[1], refs);
  }
}
const current = listBuiltinTools().sort((a, b) => a.name.localeCompare(b.name));
const currentNames = new Set(current.map(t => t.name));
const report = {
  schemaVersion: 1, legacyRevision: baseline,
  scope: "All tracked src/agents Python modules; literal names in _register_builtin_tool calls in builtin *registration.py only. Dynamic aliases, SDK wire behavior and semantic equality are NOT inferred.",
  legacyPythonFiles: paths.length, packageMarkers,
  domains: groups,
  legacyRegisteredNames: [...legacyNames].sort(([a], [b]) => a.localeCompare(b)).map(([name, sources]) => ({ name, sources, disposition: currentNames.has(name) ? "same_name_present_semantics_pending" : "missing_name_requires_review" })),
  currentTools: current.map(tool => ({ ...tool, disposition: "retained_compatibility_pending_B1_contract_audit" }))
};
const target = "docs/baseline/migration-inventory.json";
const serialized = JSON.stringify(report, null, 2) + "\n";
if (process.argv.includes("--check")) {
  if (await readFile(target, "utf8") !== serialized) throw Error("Migration inventory drift; regenerate and review changes");
} else await writeFile(target, serialized);
console.log(JSON.stringify({ legacyRevision: baseline, files: paths.length, domains: groups.length, legacyRegisteredNames: legacyNames.size, currentTools: current.length, missingNames: [...legacyNames.keys()].filter(name => !currentNames.has(name)) }));
