export type SdkActiveTurnRegistration = {
  signal: AbortSignal;
  sleepWake: SdkSleepWakeContext;
  bindRunId(runId: string): void;
  finish(): void;
};

export type SdkSleepWakeContext = {
  wait(milliseconds: number): Promise<boolean>;
  isWakeRequested(): boolean;
};

export type SdkTurnInterruptTarget = {
  sessionId?: string;
  runId?: string;
};

export type SdkActiveTurnStart = {
  sessionId: string;
  userMessageUuid?: string;
  isWakeRequested?: () => boolean;
};

type SdkActiveTurn = {
  sessionId: string;
  runId: string;
  userMessageUuid: string;
  controller: AbortController;
  wakeWaiters: Set<() => void>;
  isWakeRequested?: () => boolean;
  finished: boolean;
};

export class SdkActiveTurns {
  private readonly turnsBySessionId = new Map<string, SdkActiveTurn>();
  private readonly turnsByRunId = new Map<string, SdkActiveTurn>();
  private readonly turnsByUserMessageUuid = new Map<string, SdkActiveTurn>();

  start(input: SdkActiveTurnStart): SdkActiveTurnRegistration {
    const sessionId = input.sessionId.trim();
    const turn: SdkActiveTurn = {
      sessionId,
      runId: "",
      userMessageUuid: String(input.userMessageUuid || "").trim(),
      controller: new AbortController(),
      wakeWaiters: new Set(),
      isWakeRequested: input.isWakeRequested,
      finished: false
    };
    if (sessionId) this.turnsBySessionId.set(sessionId, turn);
    if (turn.userMessageUuid) this.turnsByUserMessageUuid.set(turn.userMessageUuid, turn);
    return {
      signal: turn.controller.signal,
      sleepWake: {
        wait: (milliseconds) => this.waitForWake(turn, milliseconds),
        isWakeRequested: () => this.isWakeRequested(turn)
      },
      bindRunId: (runId) => this.bindRunId(turn, runId),
      finish: () => this.finish(turn)
    };
  }

  wake(target: SdkTurnInterruptTarget = {}): Record<string, unknown> {
    const turns = this.wakeTargetTurns(target);
    for (const turn of turns) this.wakeTurn(turn);
    return { woken: turns.length };
  }

  interrupt(target: SdkTurnInterruptTarget = {}): Record<string, unknown> {
    const turn = this.findActiveTurn(target);
    if (!turn) {
      return {
        interrupted: false,
        reason: "no active SDK turn is attached to this control handler"
      };
    }
    return this.abortTurn(turn, "interrupted");
  }

  cancelAsyncMessage(messageUuid: string): Record<string, unknown> {
    const resolvedMessageUuid = messageUuid.trim();
    if (!resolvedMessageUuid) throw new Error("messageUuid is required");
    const turn = this.turnsByUserMessageUuid.get(resolvedMessageUuid);
    if (!turn) return { cancelled: false };
    return {
      cancelled: true,
      ...this.abortTurn(turn, "cancelled")
    };
  }

  private bindRunId(turn: SdkActiveTurn, runId: string): void {
    const resolvedRunId = runId.trim();
    if (!resolvedRunId) return;
    if (turn.runId) this.turnsByRunId.delete(turn.runId);
    turn.runId = resolvedRunId;
    this.turnsByRunId.set(resolvedRunId, turn);
  }

  private finish(turn: SdkActiveTurn): void {
    turn.finished = true;
    this.wakeTurn(turn);
    if (turn.sessionId && this.turnsBySessionId.get(turn.sessionId) === turn) {
      this.turnsBySessionId.delete(turn.sessionId);
    }
    if (turn.runId && this.turnsByRunId.get(turn.runId) === turn) {
      this.turnsByRunId.delete(turn.runId);
    }
    if (turn.userMessageUuid && this.turnsByUserMessageUuid.get(turn.userMessageUuid) === turn) {
      this.turnsByUserMessageUuid.delete(turn.userMessageUuid);
    }
  }

  private findActiveTurn(target: SdkTurnInterruptTarget): SdkActiveTurn | undefined {
    return this.targetTurns(target)[0];
  }

  private targetTurns(target: SdkTurnInterruptTarget): SdkActiveTurn[] {
    const sessionId = String(target.sessionId || "").trim();
    if (sessionId) {
      const turn = this.turnsBySessionId.get(sessionId);
      return turn ? [turn] : [];
    }
    const runId = String(target.runId || "").trim();
    if (runId) {
      const turn = this.turnsByRunId.get(runId);
      return turn ? [turn] : [];
    }
    const activeTurns = uniqueTurns([
      ...this.turnsBySessionId.values(),
      ...this.turnsByRunId.values()
    ]);
    return activeTurns.length === 1 ? activeTurns : [];
  }

  private wakeTargetTurns(target: SdkTurnInterruptTarget): SdkActiveTurn[] {
    const sessionId = String(target.sessionId || "").trim();
    if (sessionId) {
      const turn = this.turnsBySessionId.get(sessionId);
      return turn ? [turn] : [];
    }
    const runId = String(target.runId || "").trim();
    if (runId) {
      const turn = this.turnsByRunId.get(runId);
      return turn ? [turn] : [];
    }
    return uniqueTurns([
      ...this.turnsBySessionId.values(),
      ...this.turnsByRunId.values()
    ]);
  }

  private abortTurn(turn: SdkActiveTurn, action: "interrupted" | "cancelled"): Record<string, unknown> {
    if (turn.controller.signal.aborted) {
      return {
        [action]: false,
        reason: "SDK turn is already interrupted",
        sessionId: turn.sessionId,
        runId: turn.runId
      };
    }
    turn.controller.abort("interrupt");
    this.wakeTurn(turn);
    return {
      [action]: true,
      sessionId: turn.sessionId,
      runId: turn.runId
    };
  }

  private async waitForWake(turn: SdkActiveTurn, milliseconds: number): Promise<boolean> {
    if (this.isWakeRequested(turn)) return true;
    const boundedMilliseconds = Math.max(0, milliseconds);
    if (boundedMilliseconds <= 0 || turn.finished) return false;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    let wakeResolver: (() => void) | undefined;
    try {
      const wakePromise = new Promise<"wake">((resolve) => {
        wakeResolver = () => resolve("wake");
        turn.wakeWaiters.add(wakeResolver);
      });
      const timeoutPromise = new Promise<"timeout">((resolve) => {
        timeout = setTimeout(() => resolve("timeout"), boundedMilliseconds);
      });
      const result = await Promise.race([wakePromise, timeoutPromise]);
      return result === "wake" && this.isWakeRequested(turn);
    } finally {
      if (timeout) clearTimeout(timeout);
      if (wakeResolver) turn.wakeWaiters.delete(wakeResolver);
    }
  }

  private isWakeRequested(turn: SdkActiveTurn): boolean {
    if (turn.finished) return false;
    try {
      return Boolean(turn.isWakeRequested?.());
    } catch {
      return false;
    }
  }

  private wakeTurn(turn: SdkActiveTurn): void {
    const waiters = [...turn.wakeWaiters];
    turn.wakeWaiters.clear();
    for (const waiter of waiters) waiter();
  }
}

function uniqueTurns(turns: SdkActiveTurn[]): SdkActiveTurn[] {
  return [...new Set(turns)];
}
