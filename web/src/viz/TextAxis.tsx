import { useState } from "react";
import { orderedBeats, laneMarks, layoutLane, type LaneItem, type PlacedLaneItem } from "../lib/axis";
import { spline, beatsToPoints } from "../lib/spline";
import type { VizData } from "../types";

const X0 = 92, X1 = 940, ROW_H = 26, LABEL_MAX = 10;
const trunc = (s: string, n = LABEL_MAX) => (s.length > n ? s.slice(0, n) + "…" : s);
// 水平佔位 ≈ 點 + 標籤寬(中文每字約 12.5px)+ 緩衝;長標籤自動讓出空間
const gapOf = (it: LaneItem) => 22 + trunc(it.node.label).length * 12.5;

function Lane({ title, color, placed, top, hoverId, setHover, onPick }: {
  title: string; color: string; placed: PlacedLaneItem[]; top: number;
  hoverId: string | null; setHover: (id: string | null) => void; onPick: (id: string) => void;
}) {
  return (
    <g>
      <line x1={X0} y1={top} x2={X1} y2={top} stroke="#3f3a2c" strokeWidth={1} />
      <text x={X0 - 12} y={top + 4} fill="#9a9079" fontSize={12} textAnchor="end">{title}</text>
      {placed.length === 0 && <text x={X0 + 6} y={top + 18} fill="#5f5947" fontSize={11.5}>(無)</text>}
      {placed.map(p => {
        const on = hoverId === p.node.id;
        const y = top + 16 + p.level * ROW_H;
        const intensity = p.node.intensity ?? 0.4;
        const r = (3 + intensity * 2.6) * (on ? 1.35 : 1);
        const quote = p.node.evidence.find(e => e.quote)?.quote ?? "";
        return (
          <g key={p.node.id} className="cnode" data-id={p.node.id} style={{ cursor: "pointer" }}
            onMouseEnter={() => setHover(p.node.id)} onMouseLeave={() => setHover(null)}
            onClick={() => onPick(p.node.id)}>
            <line x1={p.x} y1={top} x2={p.x} y2={y} stroke={color} strokeWidth={1} opacity={on ? 0.85 : 0.4} />
            <circle cx={p.x} cy={y} r={r} fill={color} opacity={on ? 1 : 0.92} />
            <text data-label={p.node.id} x={p.x + r + 5} y={y + 4} fontSize={11.5}
              fill={on ? "#f3ecd6" : "#cfc6ac"}>{trunc(p.node.label)}</text>
            {on && quote && (
              <text x={p.x} y={y - 11} fontSize={10.5} fill="#9c8c5e" textAnchor="middle">
                {trunc(quote, 22)}
              </text>
            )}
          </g>
        );
      })}
    </g>
  );
}

export default function TextAxis({ viz, onPick }: { viz: VizData; onPick: (id: string) => void }) {
  const [hoverId, setHover] = useState<string | null>(null);

  // 張力帶(脊椎):依 precedes 排序的 beat 強度
  const yb = 200, amp = 138;
  const beats = orderedBeats(viz);
  const vals = beats.map(b => b.intensity ?? 0.3);
  const pts = beatsToPoints(vals, X0, X1, yb, amp);
  const d = spline(pts);

  // 兩條泳道:技法、效果(各自去重疊堆疊)
  const tech = layoutLane(laneMarks(viz, "technique"), X0, X1, gapOf);
  const eff = layoutLane(laneMarks(viz, "effect"), X0, X1, gapOf);
  const levels = (a: PlacedLaneItem[]) => (a.length ? Math.max(...a.map(p => p.level)) + 1 : 1);

  const TECH_TOP = 248;
  const techH = levels(tech) * ROW_H + 18;
  const EFF_TOP = TECH_TOP + techH + 26;
  const effH = levels(eff) * ROW_H + 18;
  const H = EFF_TOP + effH + 34;

  return (
    <svg className="viz" viewBox={`0 0 1000 ${H}`}>
      {/* 張力帶 */}
      <text x={X0 - 12} y={yb - amp / 2} fill="#9a9079" fontSize={12} textAnchor="end">張力</text>
      <line x1={X0} y1={yb} x2={X1} y2={yb} stroke="#5b5440" strokeWidth={1} />
      {pts.length > 0 && <>
        <path d={`${d} L${X1},${yb} L${X0},${yb} Z`} fill="rgba(230,201,138,.14)" />
        <path d={d} fill="none" stroke="var(--bone)" strokeWidth={2.4} strokeLinecap="round"
          style={{ filter: "drop-shadow(0 0 6px rgba(240,228,200,.5))" }} />
        {pts.map((p, i) => (
          <line key={`r${i}`} className="rib" x1={p[0]} y1={yb} x2={p[0]} y2={p[1]}
            stroke="#dccfae" strokeWidth={1} opacity={0.5} />
        ))}
        {pts.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r={2.4} fill="#f3ead2" />)}
      </>}

      <Lane title="技法" color="var(--c-technique)" placed={tech} top={TECH_TOP}
        hoverId={hoverId} setHover={setHover} onPick={onPick} />
      <Lane title="效果" color="var(--c-effect)" placed={eff} top={EFF_TOP}
        hoverId={hoverId} setHover={setHover} onPick={onPick} />

      <text x={X0} y={H - 10} fill="#9a9079" fontSize={13}>開頭</text>
      <text x={X1} y={H - 10} fill="#9a9079" fontSize={13} textAnchor="end">結尾</text>
    </svg>
  );
}
