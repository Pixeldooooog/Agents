import type { SdkWireMessage } from "./sdkControlTypes.js";
import { readSdkStdinJsonlTransport, type SdkJsonlTransport, writeSdkStdoutJsonlTransport } from "./sdkJsonlTransport.js";
import { SdkMessageQueue } from "./sdkMessageQueue.js";
import { SdkStructuredIo } from "./sdkStructuredIo.js";

export type SdkJsonlTransportRunnerOptions = {
  structuredIo?: SdkStructuredIo;
  closeTransport?: boolean;
  closeTransportOnInputEnd?: boolean;
  closeStructuredIoOnInputEnd?: boolean;
  onInboundMessage?: (message: SdkWireMessage) => void | Promise<void>;
  onError?: (error: unknown) => void | Promise<void>;
};

export class SdkJsonlTransportRunner {
  readonly structuredIo: SdkStructuredIo;
  private readonly inboundMessages = new SdkMessageQueue<SdkWireMessage>();
  private readLoop?: Promise<void>;
  private writeLoop?: Promise<void>;
  private started = false;
  private stopping = false;
  private transportClosed = false;
  private failure: unknown;

  constructor(
    private readonly transport: SdkJsonlTransport,
    private readonly options: SdkJsonlTransportRunnerOptions = {}
  ) {
    this.structuredIo = options.structuredIo || new SdkStructuredIo();
  }

  start(): void {
    if (this.started) return;
    this.started = true;
    this.readLoop = this.runReadLoop();
    this.writeLoop = this.runWriteLoop();
  }

  async *messages(): AsyncIterable<SdkWireMessage> {
    this.start();
    while (true) {
      const message = await this.inboundMessages.shift();
      if (!message) return;
      yield message;
    }
  }

  async wait(): Promise<void> {
    this.start();
    await Promise.all([this.readLoop!, this.writeLoop!]);
  }

  async close(): Promise<void> {
    if (this.stopping) return;
    this.stopping = true;
    this.structuredIo.close();
    this.inboundMessages.close();
    await Promise.allSettled([this.writeLoop].filter(Boolean) as Promise<void>[]);
    if (this.options.closeTransport !== false) await this.closeTransport();
    if (this.options.closeTransport !== false) {
      await Promise.allSettled([this.readLoop].filter(Boolean) as Promise<void>[]);
    }
  }

  private async runReadLoop(): Promise<void> {
    try {
      for await (const message of readSdkStdinJsonlTransport(this.transport)) {
        if (this.stopping) return;
        const inboundMessage = await this.structuredIo.receive(message);
        if (!inboundMessage) continue;
        await this.options.onInboundMessage?.(inboundMessage);
        this.inboundMessages.push(inboundMessage);
      }
      if (this.options.closeStructuredIoOnInputEnd !== false) this.structuredIo.close();
      this.inboundMessages.close();
    } catch (error) {
      await this.fail(error);
      throw error;
    } finally {
      if (this.options.closeTransport !== false && this.options.closeTransportOnInputEnd !== false) {
        await this.closeTransport();
      }
    }
  }

  private async runWriteLoop(): Promise<void> {
    try {
      while (true) {
        const message = await this.structuredIo.nextOutboundMessage();
        if (!message) return;
        await writeSdkStdoutJsonlTransport(this.transport, message);
      }
    } catch (error) {
      await this.fail(error);
      throw error;
    }
  }

  private async fail(error: unknown): Promise<void> {
    this.structuredIo.close();
    this.inboundMessages.fail(error);
    if (this.failure !== undefined) return;
    this.failure = error;
    await this.options.onError?.(error);
    if (this.options.closeTransport !== false) await this.closeTransport();
  }

  private async closeTransport(): Promise<void> {
    if (this.transportClosed) return;
    this.transportClosed = true;
    await this.transport.close();
  }
}
