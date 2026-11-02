export function clock(sec: number): string {
  const s = Number.isFinite(sec) && sec > 0 ? Math.floor(sec) : 0;
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function stepOf(sseStep: string | null, state: string): "observe" | "notes" {
  if (sseStep) return sseStep === "reviewer" ? "notes" : "observe";
  return state === "notes-running" ? "notes" : "observe";
}
