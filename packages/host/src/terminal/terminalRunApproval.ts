import type { HostServices } from "../services/hostServices.js";
import type { TerminalEventWriter } from "./terminalEventWriter.js";

export async function resumeTerminalApproval(services: HostServices, writer: TerminalEventWriter, runId: string, approvalId: string, approved: boolean): Promise<void> {
  try {
    const { result } = await services.runs.resumeApproval(runId, approved, {
      approvalId,
      stream: true,
      onEvent: event => writer.runtimeEvent(event)
    });
    writer.write({ type: "turn_finished", status: result.status, run_id: runId });
  } catch (error) {
    writer.write({ type: "error", message: error instanceof Error ? error.message : "approval failed" });
  }
}
