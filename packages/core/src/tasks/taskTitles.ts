export function defaultTaskTitle(message: string): string {
  return message.replace(/\s+/g, " ").trim().slice(0, 80) || "Untitled task";
}
