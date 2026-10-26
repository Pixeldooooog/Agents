import { disabledSkills } from "../extensions/extensionSkillEnablement.js";
import { readFile } from "node:fs/promises";
import path from "node:path";
import type { Settings } from "../config/settings.js";
import { discoverSkills } from "../extensions/extensionManifests.js";
import { memoryContextBlock, memoryScopeFromSpec } from "../memory/memoryRecords.js";
import { defaultEnabledTools } from "../models/modelProfiles.js";
import type { StateStore } from "../ports/stateStore.js";
import type { AgentSpec } from "../types/agentTypes.js";
import type { Message } from "../types/runtimeTypes.js";

export async function runtimeStartMessages(settings: Settings, store: StateStore | undefined, spec: AgentSpec, message: string, history: Message[] = []): Promise<Message[]> {
  const system = [spec.system_prompt || settings.agent.systemPrompt || "You are a precise, helpful agent."];
  const memoryContext = await memoryContextFor(settings, store, spec);
  if (memoryContext) system.push(memoryContext);
  const skills = skillInvocationAvailable(settings, spec) ? await skillMetadataInstructions(settings.repoRoot, spec) : "";
  if (skills) system.push(skills);
  const workspace = await workspaceInstructions(settings.repoRoot, spec);
  if (workspace) system.push(workspace);
  return [
    { role: "system", content: system.filter(Boolean).join("\n\n") },
    ...history.filter(item => item.role !== "system"),
    { role: "user", content: message }
  ];
}

export async function workspaceInstructions(repoRoot: string, spec: AgentSpec): Promise<string> {
  if (truthy(spec.metadata.omit_workspace_instructions)) return "";
  for (const filename of ["AGENTS.md", "CLAUDE.md"]) {
    try {
      const content = await readFile(path.join(repoRoot, filename), "utf8");
      return `Workspace instructions from ${filename}:\n${content.trim()}`;
    } catch {
      continue;
    }
  }
  return "";
}

export async function skillMetadataInstructions(repoRoot: string, spec: AgentSpec): Promise<string> {
  if (truthy(spec.metadata.omit_skill_instructions)) return "";
  const disabled = disabledSkills(spec);
  const skills = (await discoverSkills({ repoRoot })).filter(skill => !skill.invalid && !skill.disable_model_invocation && !disabled.has(skill.name));
  if (!skills.length) return "";
  return [
    "Available skills (metadata only). When a skill is relevant, call the Skill tool with its name to load the SKILL.md instructions before using it:",
    ...skills.map((skill) => `- ${skill.name}: ${compactText(skill.description)}`)
  ].join("\n");
}

async function memoryContextFor(settings: Settings, store: StateStore | undefined, spec: AgentSpec): Promise<string> {
  if (!store || settings.agent.memoryContextLimit <= 0) return "";
  if (!spec.tenant_id || !spec.user_id) return "";
  const memories = await store.listMemories({
    ...memoryScopeFromSpec(spec),
    limit: settings.agent.memoryContextLimit
  });
  return memoryContextBlock(memories, settings.agent.memoryContextLimit);
}

function truthy(value: unknown): boolean {
  return ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

function skillInvocationAvailable(settings: Settings, spec: AgentSpec): boolean {
  const tools = spec.enabled_tools.length ? spec.enabled_tools : defaultEnabledTools(settings);
  return !tools.length || tools.includes("skill.invoke");
}

function compactText(value: string): string {
  const text = value.replace(/\s+/g, " ").trim();
  return text.length <= 500 ? text : `${text.slice(0, 497)}...`;
}
