import type { StateFile } from "./stateFile.js";

export type ReadState = () => Promise<StateFile>;
export type MutateState = <T>(change: (state: StateFile) => T) => Promise<T>;
