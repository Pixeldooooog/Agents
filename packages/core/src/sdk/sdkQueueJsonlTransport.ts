import { SdkMessageQueue } from "./sdkMessageQueue.js";
import type { SdkJsonlChunk } from "./sdkJsonl.js";
import type { SdkJsonlTransport } from "./sdkJsonlTransport.js";

export class SdkQueueJsonlTransport implements SdkJsonlTransport {
  private readonly inbound = new SdkMessageQueue<SdkJsonlChunk>();
  private readonly outbound = new SdkMessageQueue<string>();
  private closedState = false;
  private inputClosed = false;

  get isClosed(): boolean {
    return this.closedState;
  }

  get closed(): boolean {
    return this.closedState;
  }

  send(chunk: SdkJsonlChunk): void {
    if (this.closedState) throw new Error("SDK JSONL transport is closed");
    if (this.inputClosed) throw new Error("SDK JSONL transport input is closed");
    this.inbound.push(chunk);
  }

  closeInput(): void {
    this.inputClosed = true;
    this.inbound.close();
  }

  close_input(): void {
    this.closeInput();
  }

  read(): Promise<SdkJsonlChunk | undefined> {
    return this.inbound.shift();
  }

  async write(data: string): Promise<void> {
    if (this.closedState) throw new Error("SDK JSONL transport is closed");
    this.outbound.push(data);
  }

  receive(): Promise<string | undefined> {
    return this.outbound.shift();
  }

  drainOutput(): string[] {
    return this.outbound.drain();
  }

  drain_output(): string[] {
    return this.drainOutput();
  }

  close(): void {
    if (this.closedState) return;
    this.closedState = true;
    this.inputClosed = true;
    this.inbound.close();
    this.outbound.close();
  }
}
