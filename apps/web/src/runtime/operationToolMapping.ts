export function isEditTool(toolName: string) {
  return toolName === "notebook.edit"
    || toolName.startsWith("filesystem.write")
    || toolName.startsWith("filesystem.delete")
    || toolName.startsWith("filesystem.move")
    || toolName.startsWith("patch.");
}

export function fileTarget(args: Record<string, any>) {
  return args.path || args.notebook_path;
}
