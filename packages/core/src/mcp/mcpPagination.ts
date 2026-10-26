/** Bounds both memory and work; repeated cursors are protocol failures, never silent truncation. */
export async function collectMcpPages<T>(read: (cursor?: string) => Promise<{ items: T[]; nextCursor?: string }>): Promise<T[]> {
  const items: T[] = [];
  const cursors = new Set<string>();
  let cursor: string | undefined;
  for (let pageNumber = 0; pageNumber < 64; pageNumber++) {
    const page = await read(cursor);
    if (!Array.isArray(page.items) || items.length + page.items.length > 1024) throw new Error("MCP discovery exceeds 1024 items or has invalid items");
    items.push(...page.items);
    if (page.nextCursor === undefined) return items;
    if (typeof page.nextCursor !== "string" || !page.nextCursor || cursors.has(page.nextCursor)) throw new Error("invalid or repeated MCP pagination cursor");
    cursors.add(page.nextCursor);
    cursor = page.nextCursor;
  }
  throw new Error("MCP discovery exceeds 64 pages");
}
