import { layoutChain, focusSet, type ChainNode } from "../lib/chain";
import type { VizData } from "../types";

const HUE: Record<string, string> = {
  technique: "var(--c-technique)", effect: "var(--c-effect)", theme: "var(--c-theme)",
};
const FLAG: Record<string, string> = { orphan: "⚑ 孤兒技法", overloaded: "⚑ 過載", hollow: "⚑ 單薄" };
const rad = (n: ChainNode) => (n.type === "theme" ? (n.classes.includes("overloaded") ? 11 : 7) : 6);

export default function IntentionChain(
  { viz, selected, onPick }: { viz: VizData; selected: string | null; onPick: (id: string | null) => void },
) {
  const { nodes, edges } = layoutChain(viz, 440);
  const byId = new Map(nodes.map(n => [n.id, n]));
  const hot = selected ? focusSet(edges, selected) : null;
  const dim = (id: string) => (hot ? !hot.has(id) : false);
  return (
    <svg className="viz" viewBox="0 0 1000 460" onClick={() => onPick(null)}>
      {[["技法", 210], ["效果", 520], ["主題", 830]].map(([t, x]) => (
        <text key={t as string} x={x as number} y={40} fill="#8f876f" fontSize={12}
          textAnchor="middle" letterSpacing="3">{t}</text>
      ))}
      {edges.map((e, i) => {
        const A = byId.get(e.from)!, B = byId.get(e.to)!;
        const on = selected === e.from || selected === e.to;
        const cls = "thread" + (selected ? (on ? " hot" : " dim") : "");
        return <path key={i} className={cls} fill="none"
          d={`M${A.x + rad(A)},${A.y} C${(A.x + B.x) / 2},${A.y} ${(A.x + B.x) / 2},${B.y} ${B.x - rad(B)},${B.y}`} />;
      })}
      {nodes.map(n => {
        const anchor = n.type === "theme" ? "start" : n.type === "technique" ? "end" : "middle";
        const tx = n.type === "theme" ? n.x + 18 : n.type === "technique" ? n.x - 14 : n.x;
        const ty = n.type === "effect" ? n.y - 12 : n.y + 4;
        const flag = n.classes.find(c => c in FLAG);
        return (
          <g key={n.id} className={`cnode ${n.classes.join(" ")}`} data-id={n.id}
            style={{ cursor: "pointer", opacity: dim(n.id) ? 0.16 : 1 }}
            onClick={(ev) => { ev.stopPropagation(); onPick(n.id); }}>
            <circle cx={n.x} cy={n.y} r={rad(n)} fill={HUE[n.type] || "#f3ead2"}
              style={n.classes.includes("overloaded") ? { filter: "drop-shadow(0 0 10px var(--c-theme))" } : undefined}
              opacity={n.classes.includes("hollow") ? 0.55 : 1} />
            <text x={tx} y={ty} fill="#e8ddc2" fontSize={13} textAnchor={anchor}>{n.label}</text>
            {flag && <text x={tx} y={n.type === "effect" ? n.y - 28 : n.y + 20} fill="#a8884a"
              fontSize={10.5} textAnchor={anchor}>{FLAG[flag]}</text>}
          </g>
        );
      })}
    </svg>
  );
}
