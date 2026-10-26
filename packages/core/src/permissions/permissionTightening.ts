const profileStrictness: Record<string, number> = { auto: 0, ask: 1, deny: 2 };

/** Within a run, tools may move the permission profile toward stricter modes only (auto → ask → deny). */
export function assertPermissionProfileTightening(current: string, next: string): void {
  if (strictness(next) < strictness(current)) {
    throw new Error(`permission_tightening_only: cannot change permission profile from ${current} to ${next} during a run`);
  }
}

// Unknown profiles gate like auto (neither ask nor deny), so they rank as the least strict.
function strictness(profile: string): number {
  return profileStrictness[profile] ?? 0;
}
