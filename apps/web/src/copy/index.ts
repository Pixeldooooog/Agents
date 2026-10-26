import { zhCN } from "./zh-CN";

/** Active locale. A future `en.ts` must satisfy the same `Copy` shape. */
export const copy = zhCN;

export function statusLabel(status: string) {
  return copy.status[status] || status;
}
