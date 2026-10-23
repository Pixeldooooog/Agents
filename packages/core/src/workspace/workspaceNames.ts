export function safeName(value: unknown, kind: string): string {
  const text = String(value || "").trim();
  const name = [...text].filter((char) => /[a-zA-Z0-9_.-]/.test(char)).join("").replace(/^[.-]+|[.-]+$/g, "");
  if (!name) throw new Error("name is required");
  if (text.includes("/") || text.includes("\\") || name === "." || name === "..") throw new Error(`${kind} name must not contain path separators`);
  return name;
}
