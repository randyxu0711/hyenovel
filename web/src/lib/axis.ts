import type { VizData, VizNode } from "../types";

export function orderedBeats(viz: VizData): VizNode[] {
  const beats = viz.nodes.filter(n => n.type === "beat");
  const byId = new Map(beats.map(b => [b.id, b]));
  const next = new Map<string, string>();
  const hasIncoming = new Set<string>();
  for (const e of viz.edges) if (e.type === "precedes" && byId.has(e.from) && byId.has(e.to)) {
    next.set(e.from, e.to); hasIncoming.add(e.to);
  }
  const start = beats.find(b => !hasIncoming.has(b.id));
  if (!start || next.size === 0) return beats;            // 沒鏈就照原序
  const out: VizNode[] = []; const seen = new Set<string>();
  let cur: string | undefined = start.id;
  while (cur && byId.has(cur) && !seen.has(cur)) { seen.add(cur); out.push(byId.get(cur)!); cur = next.get(cur); }
  for (const b of beats) if (!seen.has(b.id)) out.push(b);  // 落單的補回
  return out;
}

export function axisMarks(viz: VizData): { node: VizNode; pos: number }[] {
  const out: { node: VizNode; pos: number }[] = [];
  for (const n of viz.nodes) {
    if (n.type !== "technique" && n.type !== "effect") continue;
    const ev = n.evidence.find(e => e.pos != null);
    if (ev && ev.pos != null) out.push({ node: n, pos: ev.pos });
  }
  return out.sort((a, b) => a.pos - b.pos);
}
