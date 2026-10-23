export function terminalCommandCatalog() {
  return [
    command("/status", "Show runtime status"),
    command("/model", "Pick or switch model", "<profile>"),
    command("/sessions", "List saved sessions"),
    command("/resume", "Resume a saved session", "<session>"),
    command("/session", "Show current session"),
    command("/agents", "List agents"),
    command("/tasks", "List tasks"),
    command("/capabilities", "Show capabilities"),
    command("/plugins", "List plugins"),
    command("/permissions", "Show permissions"),
    command("/prompt", "Inspect prompt"),
    command("/skills", "List skills"),
    command("/mcp", "Show MCP configuration"),
    command("/memory", "Show memory"),
    command("/diff", "Show workspace diff"),
    command("/exit", "Exit", "", "always")
  ];
}

function command(name: string, description: string, argumentHint = "", availability: "idle" | "always" = "idle") {
  return { name, description, argumentHint, availability, source: "typescript" };
}
