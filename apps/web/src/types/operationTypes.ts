export type OperationSceneKind = "workspace" | "edit" | "web" | "browser" | "terminal" | "git" | "document" | "summary";
export type OperationPhase = "opening" | "running" | "closing" | "done" | "error";

export type OperationEvent = {
  id: string;
  runId: string;
  toolCallId: string;
  toolName: string;
  scene: OperationSceneKind;
  phase: OperationPhase;
  title: string;
  target?: string;
  detail?: string;
  argsPreview?: Record<string, unknown>;
  resultPreview?: unknown;
  diffPreview?: unknown;
  artifacts?: unknown[];
  sources?: OperationSource[];
  files?: OperationFile[];
  stats?: Record<string, unknown>;
  sequence?: number;
  source?: string;
  step?: OperationStep;
  startedAt?: number;
  endedAt?: number;
};

export type OperationStep = {
  label: string;
  detail?: string;
};

export type OperationSource = {
  title: string;
  url: string;
  domain?: string;
  content?: string;
  score?: number;
};

export type OperationFile = {
  path: string;
  kind?: string;
  status?: string;
};
