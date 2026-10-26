import { mkdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { emptyState, normalizeState, type StateFile } from "./stateFile.js";

// Shared by all instances addressing this file in one process; not a cross-process lease.
const mutations = new Map<string, Promise<void>>();

export class JsonStatePersistence {
  private readonly filename: string;

  constructor(filename: string) { this.filename = path.resolve(filename); }

  async mutate<T>(change: (state: StateFile) => T): Promise<T> {
    const operation = (mutations.get(this.filename) ?? Promise.resolve()).then(async () => {
      const state = await this.read();
      const result = change(state);
      await this.write(state);
      return result;
    });
    const settled = operation.then(() => undefined, () => undefined);
    mutations.set(this.filename, settled);
    try { return await operation; }
    finally { if (mutations.get(this.filename) === settled) mutations.delete(this.filename); }
  }

  async read(): Promise<StateFile> {
    try { return normalizeState(JSON.parse(await readFile(this.filename, "utf8"))); }
    catch (error) {
      if (error instanceof Error && "code" in error && error.code === "ENOENT") return emptyState();
      throw error;
    }
  }

  private async write(state: StateFile): Promise<void> {
    await mkdir(path.dirname(this.filename), { recursive: true });
    const temporary = `${this.filename}.${crypto.randomUUID()}.tmp`;
    try {
      await writeFile(temporary, `${JSON.stringify(state, null, 2)}\n`, { flag: "wx" });
      await rename(temporary, this.filename);
    } finally { await rm(temporary, { force: true }); }
  }
}
