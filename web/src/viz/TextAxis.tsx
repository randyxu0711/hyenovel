import { useState } from "react";
import { orderedBeats, axisMarks } from "../lib/axis";
import { spline, beatsToPoints } from "../lib/spline";
import type { VizData } from "../types";
import { HUE } from "./palette";

// 用 pts 線性內插求某 x 在曲線上的 y(讓技法/效果打點落在張力曲線上)
function yAtX(pts: [number, number][], x: number): number {
  if (pts.length === 0) return 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const [x1, y1] = pts[i], [x2, y2] = pts[i + 1];
    if (x >= x1 && x <= x2) { const t = (x - x1) / ((x2 - x1) || 1); return y1 + (y2 - y1) * t; }
  }
  return pts[pts.length - 1][1];
}

export default function TextAxis({ viz, onPick }: { viz: VizData; onPick: (id: string) => void }) {
  const [hoverId, setHoverId] = useState<string | null>(null);
  const x0 = 70, x1 = 930, yb = 300, amp = 200;
  const beats = orderedBeats(viz);
  const vals = beats.map(b => b.intensity ?? 0.3);
  const pts = beatsToPoints(vals, x0, x1, yb, amp);
  const d = spline(pts);
  const marks = axisMarks(viz).map(m => {
    const x = x0 + (x1 - x0) * m.pos;
    return { ...m, x, y: yAtX(pts, x) };
  });
  return (
    <svg className="viz" viewBox="0 0 1000 360">
      <line x1={x0} y1={yb} x2={x1} y2={yb} stroke="#5b5440" strokeWidth={1} />
      <text x={x0} y={yb + 26} fill="#9a9079" fontSize={13}>開頭</text>
      <text x={x1} y={yb + 26} fill="#9a9079" fontSize={13} textAnchor="end">結尾</text>
      {pts.length > 0 && <>
        <path d={`${d} L${x1},${yb} L${x0},${yb} Z`} fill="rgba(230,201,138,.16)" />
        <path d={d} fill="none" stroke="var(--bone)" strokeWidth={2.4} strokeLinecap="round"
          style={{ filter: "drop-shadow(0 0 6px rgba(240,228,200,.5))" }} />
        {pts.map((p, i) => (
          <line key={`r${i}`} className="rib" x1={p[0]} y1={yb} x2={p[0]} y2={p[1]}
            stroke="#dccfae" strokeWidth={1} opacity={0.55} />
        ))}
        {pts.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r={2.4} fill="#f3ead2" />)}
      </>}
      {marks.map((m, i) => {
        const on = hoverId === m.node.id;
        const quote = m.node.evidence.find(e => e.quote)?.quote ?? "";
        return (
          <g key={i} className="cnode" data-id={m.node.id} style={{ cursor: "pointer" }}
            onMouseEnter={() => setHoverId(m.node.id)} onMouseLeave={() => setHoverId(null)}
            onClick={() => onPick(m.node.id)}>
            <circle cx={m.x} cy={m.y} r={on ? 5 : 3.6} fill={HUE[m.node.type] || "#f3ead2"} />
            {on && <>
              <text data-label={m.node.id} x={m.x} y={m.y - 12} fill="#e6c98a" fontSize={12}
                textAnchor="middle">{m.node.label}</text>
              {quote && <text x={m.x} y={m.y - 28} fill="#9c8c5e" fontSize={10.5}
                textAnchor="middle">{quote.length > 18 ? quote.slice(0, 18) + "…" : quote}</text>}
            </>}
          </g>
        );
      })}
    </svg>
  );
}
