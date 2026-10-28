import { expect, test } from "bun:test";
import path from "node:path";
import { loadSettings, listBuiltinTools } from "@pixeldooooog/otto-core";

test("Kevin uses the compiled Otto package and keeps configured tools aligned", async () => {
  expect(import.meta.resolve("@pixeldooooog/otto-core")).toEndWith("/dist/index.js");
  const previous = process.env.AGENT_BUILTIN_TOOLS;
  try {
    delete process.env.AGENT_BUILTIN_TOOLS;
    const settings = await loadSettings(path.resolve(import.meta.dir, "../../.."));
    expect(settings.agent.builtinTools).toEqual(listBuiltinTools().map(tool => tool.name));
  } finally {
    if (previous === undefined) delete process.env.AGENT_BUILTIN_TOOLS;
    else process.env.AGENT_BUILTIN_TOOLS = previous;
  }
});
