/** Rule behaviors a tool may add during a run; both only make authorization stricter. */
export const permissionRuleBehaviorValues = ["deny", "ask"] as const;

export type PermissionRuleBehavior = typeof permissionRuleBehaviorValues[number];

export function permissionRuleBehaviorFromValue(value: unknown): PermissionRuleBehavior {
  const behavior = String(value || "").trim().toLowerCase();
  if (behavior === "allow") throw new Error("permission_tightening_only: allow rules cannot be added during a run");
  if ((permissionRuleBehaviorValues as readonly string[]).includes(behavior)) return behavior as PermissionRuleBehavior;
  throw new Error(`unknown permission behavior: ${value}`);
}
