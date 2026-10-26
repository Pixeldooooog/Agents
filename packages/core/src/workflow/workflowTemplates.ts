import { mkdir, readdir, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { readLimitedFile } from "../tools/promptTools.js";
import type { ToolContext } from "../tools/toolContracts.js";
import { relativeWorkspacePath, resolveWorkspacePath } from "../tools/toolInputs.js";
import { parseWorkflowJson, validateWorkflow, workflowPayload, workflowSummary, type WorkflowPlan } from "./workflowModels.js";

export async function listSavedWorkflows(context: ToolContext): Promise<Record<string, unknown>[]> {
  const directoryPath = resolveWorkspacePath(context.repoRoot, ".kevin/workflows");
  try {
    const entries = await readdir(directoryPath, { withFileTypes: true });
    const workflows = await Promise.all(entries.filter((entry) => entry.isFile() && entry.name.endsWith(".json")).map(async (entry) => {
      const name = entry.name.slice(0, -5);
      const filePath = path.join(directoryPath, entry.name);
      try {
        const payload = parseWorkflowJson((await readLimitedFile(filePath, 200000)).content, name);
        return workflowSummary(name, relativeWorkspacePath(context.repoRoot, filePath), payload);
      } catch (error) {
        return { name, path: relativeWorkspacePath(context.repoRoot, filePath), error: error instanceof Error ? error.message : String(error) };
      }
    }));
    return workflows.sort((a, b) => String(a.name).localeCompare(String(b.name)));
  } catch {
    return [];
  }
}

export async function readSavedWorkflow(context: ToolContext, name: string): Promise<Record<string, unknown>> {
  const filePath = workflowPath(context, name);
  const content = await readLimitedFile(filePath, 200000);
  return { name, path: relativeWorkspacePath(context.repoRoot, filePath), workflow: parseWorkflowJson(content.content, name) };
}

export async function saveWorkflowTemplate(context: ToolContext, name: string, plan: WorkflowPlan, overwrite: boolean): Promise<Record<string, unknown>> {
  const filePath = workflowPath(context, name);
  if (!overwrite && await fileExists(filePath)) throw new Error(`workflow already exists: ${name}`);

  const orderedNodes = validateWorkflow(plan);
  const payload = workflowPayload({ ...plan, nodes: orderedNodes });
  const content = `${JSON.stringify(payload, null, 2)}\n`;
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, content);

  const relativePath = relativeWorkspacePath(context.repoRoot, filePath);
  return { name, path: relativePath, bytes: Buffer.byteLength(content), workflow: workflowSummary(name, relativePath, payload) };
}

export async function deleteSavedWorkflow(context: ToolContext, name: string): Promise<Record<string, unknown>> {
  const filePath = workflowPath(context, name);
  await rm(filePath, { force: true });
  return { name, path: relativeWorkspacePath(context.repoRoot, filePath), deleted: true, result: { deleted: true } };
}

function workflowPath(context: ToolContext, name: string): string {
  return resolveWorkspacePath(context.repoRoot, `.kevin/workflows/${name}.json`);
}

async function fileExists(filePath: string): Promise<boolean> {
  try {
    return (await stat(filePath)).isFile();
  } catch {
    return false;
  }
}
