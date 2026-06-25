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

// 取單一型別(technique/effect)有定位的節點,給泳道用
export function laneMarks(viz: VizData, type: VizNode["type"]): LaneItem[] {
  const out: LaneItem[] = [];
  for (const n of viz.nodes) {
    if (n.type !== type) continue;
    const ev = n.evidence.find(e => e.pos != null);
    if (ev && ev.pos != null) out.push({ node: n, pos: ev.pos });
  }
  return out;
}

export interface LaneItem { node: VizNode; pos: number; }
export interface PlacedLaneItem extends LaneItem { x: number; level: number; }

// 在一條泳道內把點依文本位置排開;與同層前一個點的「水平佔位」重疊時往上一層堆疊。
// gapOf(it) = 該點(含標籤)需要的水平寬度 → 長標籤自動讓出更多空間,短的擠得近。
// x 永遠是真實文本位置,只有 level(縱向行)被挪動 → 加引線就能讀清楚。
export function layoutLane(
  items: LaneItem[], x0: number, x1: number, gapOf: (it: LaneItem) => number,
): PlacedLaneItem[] {
  const sorted = [...items].sort((a, b) => a.pos - b.pos);
  const lastX: number[] = [];   // 每層最後一個點的 x
  const lastGap: number[] = []; // 每層最後一個點的水平佔位
  return sorted.map(it => {
    const x = x0 + (x1 - x0) * it.pos;
    let level = 0;
    while (lastX[level] != null && x - lastX[level] < lastGap[level]) level++;
    lastX[level] = x; lastGap[level] = gapOf(it);
    return { ...it, x, level };
  });
}
