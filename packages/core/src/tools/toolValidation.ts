import Ajv, { type ValidateFunction } from "ajv";
import type { RegisteredTool } from "./toolContracts.js";

type ValidatedTool = Pick<RegisteredTool, "name" | "parameters">;

export const MAX_TOOL_INPUT_BYTES = 256 * 1024;
const ajv = new Ajv({ strict: false, allErrors: false, coerceTypes: false, useDefaults: false, removeAdditional: false, validateFormats: false });
const validators = new WeakMap<ValidatedTool, ValidateFunction>();

export function prepareToolValidator(definition: ValidatedTool): void {
  validators.set(definition, ajv.compile(definition.parameters));
}

/** Runs before the handler. Does not coerce, default, or mutate approved arguments. */
export function assertToolArguments(definition: ValidatedTool, args: unknown): void {
  if (!args || typeof args !== "object" || Array.isArray(args)) throw new Error("invalid_tool_arguments: expected object");
  let serialized: string;
  try { serialized = JSON.stringify(args); }
  catch { throw new Error("invalid_tool_arguments: not JSON serializable"); }
  if (Buffer.byteLength(serialized) > MAX_TOOL_INPUT_BYTES) throw new Error("tool_input_limit_exceeded");
  const validate = validators.get(definition);
  if (!validate) throw new Error("tool_schema_not_prepared");
  // Runtime correlation is not part of a model-facing parameter schema.
  const { tool_call_id: _correlation, ...parameters } = args as Record<string, unknown>;
  if (!validate(parameters)) {
    const error = validate.errors?.[0];
    throw new Error(`invalid_tool_arguments: ${error?.instancePath || "/"} ${error?.message || "schema mismatch"}`);
  }
}
