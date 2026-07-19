import type { VizData, VizEdge, NodeType } from "../types";

export interface ChainNode { id: string; type: NodeType; label: string; x: number; y: number; classes: string[]; }
export interface ChainEdge { from: string; to: string; kind: VizEdge["type"]; }

const COLX: Record<string, number> = { technique: 210, effect: 520, theme: 830 };

export function layoutChain(viz: VizData, h: number): { nodes: ChainNode[]; edges: ChainEdge[] } {
  const cols: Record<string, typeof viz.nodes> = { technique: [], effect: [], theme: [] };
  for (const n of viz.nodes) if (n.type in cols) cols[n.type].push(n);
  const nodes: ChainNode[] = [];
  for (const type of ["technique", "effect", "theme"]) {
    const list = cols[type], gap = h / (list.length + 1);
    list.forEach((n, i) => nodes.push({
      id: n.id, type: n.type, label: n.label, x: COLX[type], y: gap * (i + 1),
      classes: viz.diag[n.id] || [],
    }));
  }
  const keep = new Set(["produces", "serves"]);
  const ids = new Set(nodes.map(n => n.id));
  const edges = viz.edges
    .filter(e => keep.has(e.type) && ids.has(e.from) && ids.has(e.to))
    .map(e => ({ from: e.from, to: e.to, kind: e.type }));
  return { nodes, edges };
}

// 選/hover 一個節點 → 亮整條意圖鏈:沿因果方向往下(它產出/服務到的)+往上(產出它的)遞迴,
// 不只 1 跳。兩向各自從 id 出發(DAG,不會繞回),故是「這個節點的上下游錐」而非整個連通團——
// 共用同一效果的兄弟技法不會被拉進來。
export function focusSet(edges: Pick<VizEdge, "from" | "to">[], id: string): Set<string> {
  const s = new Set<string>([id]);
  const walk = (down: boolean) => {
    const q = [id];
    while (q.length) {
      const cur = q.shift()!;
      for (const e of edges) {
        const next = down ? (e.from === cur ? e.to : null) : (e.to === cur ? e.from : null);
        if (next && !s.has(next)) { s.add(next); q.push(next); }
      }
    }
  };
  walk(true); walk(false);
  return s;
}
