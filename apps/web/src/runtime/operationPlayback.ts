import type { OperationEvent, OperationPhase } from "../types";

const playbackMap: Record<OperationPhase, OperationPhase[]> = {
  opening: ["opening", "running"],
  running: ["running"],
  closing: ["closing"],
  done: ["running", "closing", "done"],
  error: ["running", "error"],
};

export function playbackFrames(event: OperationEvent): OperationEvent[] {
  if (event.source === "sandbox_trace") return [event];
  return playbackMap[event.phase].map((phase) => ({
    ...event,
    id: `${event.id}:frame:${phase}`,
    phase,
    title: titleForPhase(event.title, phase),
  }));
}

export function playbackDelay(index: number) {
  return Math.min(index * 420, 1260);
}

function titleForPhase(title: string, phase: OperationPhase) {
  if (phase === "running") return title.replace(/^Opening/, "Running").replace(/^Completed/, "Collecting");
  if (phase === "closing") return title.replace(/^Opening/, "Closing").replace(/^Completed/, "Closing");
  return title;
}
