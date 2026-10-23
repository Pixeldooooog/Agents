import type { WorktreeRequest } from "./worktreeTypes.js";

export function worktreeRequest(name: string, prNumber: number): WorktreeRequest {
  const parsedPr = parsePrReference(name);
  const explicitPr = prNumber > 0 ? prNumber : null;
  if (parsedPr && explicitPr && parsedPr !== explicitPr) {
    throw new Error(`Conflicting pull request references: name=${name} pr_number=${explicitPr}`);
  }
  const resolvedPr = explicitPr || parsedPr;
  const generatedSlug = `worktree-${crypto.randomUUID().replaceAll("-", "").slice(0, 8)}`;
  const slug = resolvedPr ? `pr-${resolvedPr}` : name || generatedSlug;
  validateSlug(slug);
  return { slug, prNumber: resolvedPr };
}

export function flattenSlug(slug: string): string {
  return slug.replaceAll("/", "+");
}

function validateSlug(slug: string): void {
  if (slug.length > 64) throw new Error("Invalid worktree name: must be 64 characters or fewer");
  for (const segment of slug.split("/")) {
    if (!segment || segment === "." || segment === ".." || !/^[A-Za-z0-9._-]+$/.test(segment)) {
      throw new Error(`Invalid worktree name "${slug}"`);
    }
  }
}

function parsePrReference(value: string): number | null {
  const text = value.trim();
  const urlMatch = /^https?:\/\/[^/]+\/[^/]+\/[^/]+\/pull\/(\d+)\/?(?:[?#].*)?$/i.exec(text);
  if (urlMatch) return Number(urlMatch[1]);
  const hashMatch = /^#(\d+)$/.exec(text);
  return hashMatch ? Number(hashMatch[1]) : null;
}
