export class SdkMessageQueue<T> {
  private messages: T[] = [];
  private waiters: ((message: T | undefined) => void)[] = [];
  private closed = false;
  private error: unknown;

  push(message: T): void {
    const waiter = this.waiters.shift();
    if (waiter) {
      waiter(message);
      return;
    }
    this.messages.push(message);
  }

  fail(error: unknown): void {
    this.error = error;
    this.close();
  }

  close(): void {
    this.closed = true;
    while (this.waiters.length) this.waiters.shift()?.(undefined);
  }

  drain(): T[] {
    const messages = this.messages;
    this.messages = [];
    return messages;
  }

  async shift(): Promise<T | undefined> {
    if (this.messages.length) return this.messages.shift();
    if (this.error) throw this.error;
    if (this.closed) return undefined;
    const message = await new Promise<T | undefined>((resolve) => this.waiters.push(resolve));
    if (message === undefined && this.error) throw this.error;
    return message;
  }
}
