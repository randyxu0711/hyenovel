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
  const keep = new Set(["produces", "serves", "manifests"]);
  const ids = new Set(nodes.map(n => n.id));
  const edges = viz.edges
    .filter(e => keep.has(e.type) && ids.has(e.from) && ids.has(e.to))
    .map(e => ({ from: e.from, to: e.to, kind: e.type }));
  return { nodes, edges };
}

export function focusSet(edges: Pick<VizEdge, "from" | "to">[], id: string): Set<string> {
  const s = new Set<string>([id]);
  for (const e of edges) { if (e.from === id) s.add(e.to); if (e.to === id) s.add(e.from); }
  return s;
}
