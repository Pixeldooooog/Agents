import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  emptyState,
  normalizeState,
  type StateFile
} from "./stateFile.js";

export class JsonStatePersistence {
  private queue = Promise.resolve();

  constructor(private readonly filename: string) {}

  async mutate<T>(change: (state: StateFile) => T): Promise<T> {
    const operation = this.queue.then(async () => {
      const state = await this.read();
      const result = change(state);
      await this.write(state);
      return result;
    });
    this.queue = operation.then(() => undefined, () => undefined);
    return operation;
  }

  async read(): Promise<StateFile> {
    try {
      return normalizeState(JSON.parse(await readFile(this.filename, "utf8")));
    } catch {
      return emptyState();
    }
  }

  private async write(state: StateFile): Promise<void> {
    await mkdir(path.dirname(this.filename), { recursive: true });
    await writeFile(this.filename, `${JSON.stringify(state, null, 2)}\n`);
  }
}
