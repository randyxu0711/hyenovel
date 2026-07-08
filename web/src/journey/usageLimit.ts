/** 把 SSE error 的 resets_at(Unix 秒)轉成右下角提示文案;null 給泛用句。 */
export function formatResetHint(resetsAt: number | null): string {
  if (!resetsAt) return "撞到訂閱用量上限,稍後再跑。";
  const t = new Date(resetsAt * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  return `撞到訂閱用量上限,${t} 額度重置後再跑。`;
}
