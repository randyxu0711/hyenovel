/** resets_at(Unix 秒)→ 本地 24h「HH:MM」;無時刻回 null(交給呼叫端給泛用句)。 */
export function formatResetTime(resetsAt: number | null): string | null {
  if (!resetsAt) return null;
  return new Date(resetsAt * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}
