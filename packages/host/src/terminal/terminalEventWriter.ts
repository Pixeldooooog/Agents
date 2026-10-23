export class TerminalEventWriter {
  write(payload: unknown): void {
    process.stdout.write(`${JSON.stringify(payload)}\n`);
  }

  runtimeEvent(event: unknown): void {
    this.write({ type: "runtime_event", event });
  }
}
