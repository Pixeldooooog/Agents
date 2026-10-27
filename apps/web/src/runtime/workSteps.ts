import type { OperationEvent } from "../types/operationTypes";

/** One entry per observed tool call; run summaries and presentation frames are not work. */
export function collectWorkSteps(events: OperationEvent[]): OperationEvent[] {
  const calls = new Map<string, OperationEvent>();
  for (const event of events) {
    if (!event.toolCallId || event.scene === "summary") continue;
    const key = `${event.runId}:${event.toolCallId}`;
    const previous = calls.get(key);
    calls.set(key, {
      ...previous,
      ...event,
      argsPreview: Object.keys(event.argsPreview || {}).length
        ? event.argsPreview
        : previous?.argsPreview,
      target:
        event.target && event.target !== event.toolName
          ? event.target
          : previous?.target || event.target,
    });
  }
  return [...calls.values()];
}

export function workStepTitle(event: OperationEvent): string {
  return toolDisplayName(event.toolName);
}

export function toolDisplayName(toolName: string): string {
  const name = toolName.replace(/__/g, ".");
  const labels: Record<string, string> = {
    "filesystem.read": "读取文件",
    "filesystem.write": "写入文件",
    "filesystem.edit": "编辑文件",
    "filesystem.list": "查看目录",
    "web.search": "搜索资料",
    "web.fetch": "阅读网页",
    "shell.run": "执行命令",
    "skill.load": "加载技能",
  };
  return labels[name] || name;
}
