export const permissionBehaviorValues = ["allow", "deny", "ask"] as const;

export type PermissionBehavior = typeof permissionBehaviorValues[number];

export function permissionBehaviorFromValue(value: unknown): PermissionBehavior {
  const behavior = String(value || "").trim().toLowerCase();
  if (isPermissionBehavior(behavior)) return behavior;
  throw new Error(`unknown permission behavior: ${value}`);
}

export function optionalPermissionBehavior(value: unknown): PermissionBehavior | "" {
  const behavior = String(value || "").trim().toLowerCase();
  if (!behavior) return "";
  if (isPermissionBehavior(behavior)) return behavior;
  throw new Error(`unknown permission behavior: ${behavior}`);
}

function isPermissionBehavior(value: string): value is PermissionBehavior {
  return permissionBehaviorValues.includes(value as PermissionBehavior);
}
