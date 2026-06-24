import { orderedBeats, axisMarks } from "../lib/axis";
import { spline, beatsToPoints } from "../lib/spline";
import type { VizData } from "../types";

const HUE: Record<string, string> = {
  technique: "var(--c-technique)", effect: "var(--c-effect)", theme: "var(--c-theme)",
};

export default function TextAxis({ viz, onPick }: { viz: VizData; onPick: (id: string) => void }) {
  const x0 = 70, x1 = 930, yb = 300, amp = 200;
  const beats = orderedBeats(viz);
  const vals = beats.map(b => b.intensity ?? 0.3);
  const pts = beatsToPoints(vals, x0, x1, yb, amp);
  const d = spline(pts);
  const marks = axisMarks(viz).map(m => ({ ...m, x: x0 + (x1 - x0) * m.pos, y: yb - (/* 落在曲線附近 */ 0.5) * amp }));
  return (
    <svg className="viz" viewBox="0 0 1000 360">
      <line x1={x0} y1={yb} x2={x1} y2={yb} stroke="#5b5440" strokeWidth={1} />
      <text x={x0} y={yb + 26} fill="#9a9079" fontSize={13}>開頭</text>
      <text x={x1} y={yb + 26} fill="#9a9079" fontSize={13} textAnchor="end">結尾</text>
      {pts.length > 0 && <>
        <path d={`${d} L${x1},${yb} L${x0},${yb} Z`} fill="rgba(230,201,138,.16)" />
        <path d={d} fill="none" stroke="var(--bone)" strokeWidth={2.4} strokeLinecap="round"
          style={{ filter: "drop-shadow(0 0 6px rgba(240,228,200,.5))" }} />
        {pts.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r={2.4} fill="#f3ead2" />)}
      </>}
      {marks.map((m, i) => (
        <g key={i} className="cnode" data-id={m.node.id} style={{ cursor: "pointer" }}
          onClick={() => onPick(m.node.id)}>
          <circle cx={m.x} cy={m.y} r={3.6} fill={HUE[m.node.type] || "#f3ead2"} />
          <text x={m.x} y={m.y - 10} fill="#cabd92" fontSize={11.5} textAnchor="middle">{m.node.label}</text>
        </g>
      ))}
    </svg>
  );
}
