import type { OperationEvent, OperationSceneKind } from "../types/runtimeTypes";

export type StageStepStatus = "done" | "active" | "pending" | "error";

export type StageStep = {
  label: string;
  detail: string;
  status: StageStepStatus;
};

export type StageEvidence = {
  label: string;
  value: string;
  tone?: "ok" | "warn" | "error";
};

export type StageScript = {
  appLabel: string;
  steps: StageStep[];
  evidence: StageEvidence[];
  command: string;
  target: string;
};

export function scriptForOperation(event: OperationEvent): StageScript {
  const baseSteps = stepTemplate(event);
  const active = activeStepIndex(event.phase, baseSteps.length);
  const steps = baseSteps.map((step, index) => index === active && event.step?.label ? { label: event.step.label, detail: event.step.detail || step.detail } : step);
  return {
    appLabel: appLabel(event.scene),
    steps: steps.map((step, index) => ({ ...step, status: stepStatus(index, active, event.phase) })),
    evidence: evidenceFor(event),
    command: commandFor(event),
    target: event.target || event.toolName,
  };
}

function stepTemplate(event: OperationEvent): Array<Omit<StageStep, "status">> {
  const target = event.target || event.toolName;
  if (event.scene === "web" || event.scene === "browser") return [
    { label: "open browser", detail: "Launch web workspace" },
    { label: "type target", detail: target },
    { label: "scan sources", detail: `${event.sources?.length || 0} candidate sources` },
    { label: "capture context", detail: "Return findings to run memory" },
  ];
  if (event.scene === "terminal" || event.scene === "git") return [
    { label: "open shell", detail: "Attach to workspace terminal" },
    { label: "run command", detail: target },
    { label: "read output", detail: event.phase === "error" ? "Command failed" : "Collect stdout and exit state" },
    { label: "record result", detail: "Persist command evidence" },
  ];
  if (event.scene === "edit") return [
    { label: "open file", detail: target },
    { label: "apply edit", detail: event.detail || "Patch workspace file" },
    { label: "save file", detail: "Write changes to disk" },
    { label: "capture diff", detail: diffSummary(event.diffPreview) || "Record edit evidence" },
  ];
  if (event.scene === "document") return [
    { label: "open source", detail: target },
    { label: "read section", detail: event.detail || "Inspect relevant context" },
    { label: "extract rules", detail: "Keep constraints for the agent" },
    { label: "attach context", detail: "Return notes to model context" },
  ];
  if (event.scene === "summary") return [
    { label: "close windows", detail: "End active tool views" },
    { label: "collect evidence", detail: `${event.artifacts?.length || 0} artifacts` },
    { label: "summarize run", detail: event.detail || "Prepare final answer" },
    { label: "return to chat", detail: "Conversation receives the result" },
  ];
  return [
    { label: "open folder", detail: "Enter workspace" },
    { label: "locate target", detail: target },
    { label: "preview content", detail: event.detail || "Read workspace state" },
    { label: "return context", detail: "Feed result back to the agent" },
  ];
}

function activeStepIndex(phase: string, count: number) {
  if (phase === "done") return count - 1;
  if (phase === "error") return Math.min(2, count - 1);
  if (phase === "closing") return Math.max(0, count - 2);
  if (phase === "running") return Math.min(1, count - 1);
  return 0;
}

function stepStatus(index: number, active: number, phase: string): StageStepStatus {
  if (phase === "error" && index === active) return "error";
  if (index < active) return "done";
  if (index === active) return "active";
  return "pending";
}

function evidenceFor(event: OperationEvent): StageEvidence[] {
  const evidence: StageEvidence[] = [];
  for (const file of event.files?.slice(0, 3) || []) evidence.push({ label: "file", value: file.path });
  for (const source of event.sources?.slice(0, 3) || []) evidence.push({ label: "source", value: source.domain || source.title });
  const diff = diffSummary(event.diffPreview);
  if (diff) evidence.push({ label: "diff", value: diff, tone: event.phase === "error" ? "error" : "ok" });
  if (event.artifacts?.length) evidence.push({ label: "artifact", value: String(event.artifacts.length) });
  if (event.stats?.duration_ms) evidence.push({ label: "time", value: `${event.stats.duration_ms} ms` });
  if (!evidence.length && event.detail) evidence.push({ label: "detail", value: event.detail });
  return evidence.slice(0, 5);
}

function commandFor(event: OperationEvent) {
  const args = event.argsPreview || {};
  if (typeof args.command === "string") return args.command;
  if (typeof args.query === "string") return args.query;
  if (typeof args.url === "string") return args.url;
  if (typeof args.path === "string") return args.path;
  return event.target || event.detail || event.toolName;
}

function appLabel(scene: OperationSceneKind) {
  if (scene === "web" || scene === "browser") return "Browser";
  if (scene === "terminal" || scene === "git") return scene === "git" ? "Git Terminal" : "Terminal";
  if (scene === "edit") return "Editor";
  if (scene === "document") return "Reader";
  if (scene === "summary") return "Summary";
  return "Finder";
}

function diffSummary(diff: unknown) {
  if (!diff) return "";
  if (typeof diff === "string") return diff.split("\n").slice(0, 2).join(" ").slice(0, 80);
  if (typeof diff !== "object") return "";
  const data = diff as Record<string, unknown>;
  const count = (key: string) => Array.isArray(data[key]) ? (data[key] as unknown[]).length : 0;
  const parts = [["+", count("created")], ["~", count("modified")], ["-", count("deleted")]]
    .filter(([, value]) => Number(value) > 0)
    .map(([label, value]) => `${label}${value}`);
  return parts.join(" ") || "";
}
