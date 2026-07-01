import { useEffect, useReducer, useRef } from "react";
import { buildBone } from "../lib/bone";
import { orderedBeats } from "../lib/axis";
import type { Pt } from "../lib/spline";
import { layoutChain, focusSet } from "../lib/chain";
import type { VizData, VizNode } from "../types";

// ── 一具密骨,三姿勢,節點守恆 ──
// calm 剪影:脊椎+肋,無字。
// axis 完整解剖:脊椎(張力)=椎節(節拍);效果=脊椎關節;技法=往下的肋;主題=往上的肋;意象=短上肋(織體)。
//   名字隨手出:主題常駐,其餘 hover/選中才浮(密肋本身=資訊;伸手要名字)。
// chain 拆骨:技法/效果/主題飛進三欄 + produces/serves 韌帶。診斷=骨上病灶。

const W = 1000, X0 = 18, X1 = W - X0;
const BONE_TOP = 158, BONE_H = 188;
const CHAIN_TOP = 120, CHAIN_H = 420;
const COLX: Record<string, number> = { technique: 210, effect: 520, theme: 830 };
const H = 580;
const PX = (pos: number) => X0 + (X1 - X0) * pos;
const trunc = (s: string, n = 9) => (s.length > n ? s.slice(0, n) + "…" : s);

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const ease = (u: number) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);
const COLOR: Record<string, string> = {
  technique: "var(--c-technique)", effect: "var(--c-effect)", theme: "var(--c-theme)", motif: "var(--c-motif)",
};
const DIAG = { over: "#e0625a", orphan: "#e8a24a" };
const firstPos = (n: VizNode) => n.evidence.find(e => e.pos != null)?.pos ?? 0.5;
const radius = (n: VizNode) => (n.type === "theme" ? 6 : n.type === "effect" ? 3.5 + (n.intensity ?? 0.4) * 3 : 4.5);
const HALO = { paintOrder: "stroke", stroke: "#0c0b09", strokeWidth: 3.4, strokeLinejoin: "round" } as const;

// 脊椎折線上求 x 處的 y 與「朝上」單位法線
function onSpine(pts: Pt[], x: number): { y: number; ux: number; uy: number } {
  for (let i = 0; i < pts.length - 1; i++) {
    const [x1, y1] = pts[i], [x2, y2] = pts[i + 1];
    if (x >= x1 && x <= x2) {
      const t = (x - x1) / ((x2 - x1) || 1), tx = x2 - x1, ty = y2 - y1, tl = Math.hypot(tx, ty) || 1;
      let ux = -ty / tl, uy = tx / tl; if (uy > 0) { ux = -ux; uy = -uy; }
      return { y: y1 + (y2 - y1) * t, ux, uy };
    }
  }
  const l = pts[pts.length - 1]; return { y: l[1], ux: 0, uy: -1 };
}

// 由節點 id 決定的確定性「亂數」(每次渲染穩定)
function hash01(s: string) {
  let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return ((h >>> 0) % 1000) / 1000;
}
// 一根有機的肋:往外微張 + 抖動 + 長短不一 + 一點彎(像真的骨,不是格尺)
function rib(bx: number, by: number, sign: number, baseLen: number, level: number, id: string) {
  const j = hash01(id), j2 = hash01(id + "*");
  const lean = (bx - W / 2) / (W / 2);                 // 離中心越遠越往外張
  const len = baseLen * (0.78 + j * 0.5) + level * 18;
  const tx = clamp(bx + lean * 26 + (j2 - 0.5) * 30, X0 + 4, X1 - 4);
  const ty = by + sign * len;
  const mx = (bx + tx) / 2, my = (by + ty) / 2, dx = tx - bx, dy = ty - by, L = Math.hypot(dx, dy) || 1;
  const bow = (j - 0.5) * 13;                           // 微彎
  return { d: `M${bx.toFixed(1)},${by.toFixed(1)} Q${(mx - dy / L * bow).toFixed(1)},${(my + dx / L * bow).toFixed(1)} ${tx.toFixed(1)},${ty.toFixed(1)}`, tx, ty };
}

type Mode = "calm" | "axis" | "chain";
interface Bridge { node: VizNode; ax: number; ay: number; bx: number; by: number; phase: number; }

export default function BoneStage(
  { viz, mode, hover, onHover, selected, onSelect }:
  { viz: VizData; mode: Mode; hover: string | null; onHover: (id: string | null) => void;
    selected: string | null; onSelect: (id: string | null) => void },
) {
  const gRef = useRef(0);
  const rafRef = useRef(0);
  const [, force] = useReducer((x: number) => x + 1, 0);
  useEffect(() => {
    const from = gRef.current, to = mode === "chain" ? 1 : 0, start = performance.now(), DUR = 950;
    const tick = (now: number) => {
      const k = clamp((now - start) / DUR);
      gRef.current = from + (to - from) * k; force();
      if (k < 1) rafRef.current = requestAnimationFrame(tick);
    };
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);
  const g = gRef.current, eP = ease(g);

  const { d, pts } = buildBone(viz, W, BONE_H);
  const beats = orderedBeats(viz);

  // 各型別在骨上的位置(bone 座標;y 之後 +BONE_TOP 成絕對)
  const recurOf = (n: VizNode) => Math.max(1, n.evidence.length);
  const themes = viz.nodes.filter(n => n.type === "theme");
  const motifs = viz.nodes.filter(n => n.type === "motif");
  const techs = viz.nodes.filter(n => n.type === "technique");
  const effects = viz.nodes.filter(n => n.type === "effect");
  const maxThemeR = Math.max(1, ...themes.map(recurOf));
  const maxMotifR = Math.max(1, ...motifs.map(recurOf));

  // 技法往下的肋:同段群聚 → 逐層加長,讓肋尖往下展開不疊
  const techLevel = new Map<string, number>();
  { const lastAt: number[] = [];
    for (const n of [...techs].sort((a, b) => firstPos(a) - firstPos(b))) {
      const x = PX(firstPos(n)); let lv = 0;
      while (lastAt[lv] != null && x - lastAt[lv] < 26) lv++;
      lastAt[lv] = x; techLevel.set(n.id, lv);
    } }

  // rib paths(bone 座標,有機散開)+ 各橋接節點的 A 落點(絕對)
  const ribPaths: { d: string; color: string; w: number; op: number }[] = [];
  const motifDots: { id: string; x: number; y: number; label: string }[] = [];   // 意象肋尖端點(非橋接、不飛)
  const themeA = new Map<string, { x: number; y: number }>();
  const techA = new Map<string, { x: number; y: number }>();
  const effA = new Map<string, { x: number; y: number }>();
  for (const n of themes) {
    const x = PX(firstPos(n)), s = onSpine(pts, x);
    const rr = rib(x, s.y, -1, 26 + (recurOf(n) / maxThemeR) * 42, 0, n.id);  // 往上
    ribPaths.push({ d: rr.d, color: "var(--c-theme)", w: 1.4, op: 0.6 });
    themeA.set(n.id, { x: rr.tx, y: rr.ty + BONE_TOP });
  }
  for (const n of motifs) {
    const x = PX(firstPos(n)), s = onSpine(pts, x);
    const rr = rib(x, s.y, -1, 13 + (recurOf(n) / maxMotifR) * 16, 0, n.id);
    ribPaths.push({ d: rr.d, color: "var(--c-motif)", w: 1, op: 0.42 });
    motifDots.push({ id: n.id, x: rr.tx, y: rr.ty, label: n.label });
  }
  for (const n of techs) {
    const x = PX(firstPos(n)), s = onSpine(pts, x);
    const rr = rib(x, s.y, 1, 30, techLevel.get(n.id) ?? 0, n.id);            // 往下;群聚→逐層加長
    ribPaths.push({ d: rr.d, color: "var(--c-technique)", w: 1, op: 0.5 });
    techA.set(n.id, { x: rr.tx, y: rr.ty + BONE_TOP });
  }
  for (const n of effects) { const x = PX(firstPos(n)), s = onSpine(pts, x); effA.set(n.id, { x, y: s.y + BONE_TOP }); }

  const chain = layoutChain(viz, CHAIN_H);
  const chainB = new Map(chain.nodes.map(n => [n.id, { x: n.x, y: n.y + CHAIN_TOP }]));

  const bridgeNodes = [...techs, ...effects, ...themes];
  const sorted = [...bridgeNodes].sort((a, b) => firstPos(a) - firstPos(b));
  const phaseOf = new Map(sorted.map((n, i) => [n.id, sorted.length > 1 ? i / (sorted.length - 1) : 0]));
  const aOf = (n: VizNode) => (n.type === "theme" ? themeA.get(n.id) : n.type === "effect" ? effA.get(n.id) : techA.get(n.id));
  const bridges: Bridge[] = bridgeNodes.map(n => {
    const b = chainB.get(n.id) ?? { x: 500, y: 300 };
    const a = aOf(n) ?? b;
    return { node: n, ax: a.x, ay: a.y, bx: b.x, by: b.y, phase: phaseOf.get(n.id) ?? 0 };
  });
  const STAG = 0.32;
  const curById = new Map(bridges.map(br => {
    const t = ease(clamp((g - br.phase * STAG) / (1 - STAG)));
    return [br.node.id, { x: lerp(br.ax, br.bx, t), y: lerp(br.ay, br.by, t) }];
  }));

  const r = radius;
  const focusId = selected ?? hover;
  const focus = focusId ? focusSet(chain.edges, focusId) : null;
  const dim = (id: string) => (focus ? (focus.has(id) ? 1 : 0.14) : 1);
  const selCur = selected ? curById.get(selected) : null;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="bonestage" width="100%"
      onMouseLeave={() => onHover(null)} onClick={() => onSelect(null)}>
      <g opacity={1 - eP}>
        <text x={X0} y={H - 12} fill="#7d745c" fontSize={12}>開頭</text>
        <text x={X1} y={H - 12} fill="#7d745c" fontSize={12} textAnchor="end">結尾</text>
      </g>
      <g opacity={eP} style={{ pointerEvents: "none" }}>
        {Object.entries(COLX).map(([t, x]) => (
          <text key={t} x={x} y={CHAIN_TOP - 30} fill="#8f876f" fontSize={12.5} textAnchor="middle" letterSpacing="4">
            {t === "technique" ? "技法" : t === "effect" ? "效果" : "主題"}
          </text>
        ))}
      </g>

      {/* 密骨:脊椎 + 椎節 + 全部肋(肋線淡出;節點本體在 bridges 飛) */}
      <g transform={`translate(0,${BONE_TOP})`} style={{ pointerEvents: eP > 0.5 ? "none" : "auto" }}>
        <path d={d} fill="none" stroke="var(--bone)" strokeWidth={2.6} strokeLinecap="round" opacity={1 - eP}
          style={{ filter: "drop-shadow(0 0 6px rgba(240,228,200,.45))" }} />
        {ribPaths.map((b, i) => (
          <path key={i} d={b.d} fill="none" stroke={b.color} strokeWidth={b.w}
            strokeLinecap="round" opacity={b.op * (1 - eP)} />
        ))}
        {beats.map((b, i) => { if (!pts[i]) return null; const on = hover === b.id, x = pts[i][0], y = pts[i][1], end = x > X1 - 150;
          return (
            <g key={`b${b.id}`} style={{ cursor: "pointer" }} onMouseEnter={() => onHover(b.id)} onMouseLeave={() => onHover(null)}>
              <circle cx={x} cy={y} r={on ? 4.5 : 2.3 + (b.intensity ?? 0.3) * 1.5} fill="var(--c-beat)"
                opacity={(1 - eP) * dim(b.id)} style={{ transition: "r .12s ease" }} />
              {on && <text x={end ? x - 7 : x + 7} y={y + 16} textAnchor={end ? "end" : "start"} fontSize={12.5} fill="#f6efd9" style={HALO} opacity={1 - eP}>{trunc(b.label)}</text>}
            </g>
          );
        })}
        {motifDots.map(m => { const on = hover === m.id, end = m.x > X1 - 150;
          return (
            <g key={`md${m.id}`} style={{ cursor: "pointer" }} onMouseEnter={() => onHover(m.id)} onMouseLeave={() => onHover(null)}>
              <circle cx={m.x} cy={m.y} r={on ? 4.5 : 3} fill="var(--c-motif)" opacity={(1 - eP) * dim(m.id)} style={{ transition: "r .12s ease" }} />
              {on && <text x={end ? m.x - 7 : m.x + 7} y={m.y - 7} textAnchor={end ? "end" : "start"} fontSize={12.5} fill="#f6efd9" style={HALO} opacity={1 - eP}>{trunc(m.label)}</text>}
            </g>
          );
        })}
      </g>

      {/* 因果韌帶 */}
      <g opacity={eP} style={{ pointerEvents: "none" }}>
        {chain.edges.map((e, i) => {
          const A = curById.get(e.from), B = curById.get(e.to);
          if (!A || !B) return null;
          const on = hover === e.from || hover === e.to, mid = (A.x + B.x) / 2;
          return <path key={i} d={`M${A.x},${A.y} C${mid},${A.y} ${mid},${B.y} ${B.x},${B.y}`}
            fill="none" stroke="var(--amber)" strokeWidth={on ? 1.8 : 1.2} opacity={hover ? (on ? 0.85 : 0.12) : 0.45} />;
        })}
      </g>

      {selCur && (
        <line x1={selCur.x} y1={selCur.y} x2={W} y2={selCur.y} stroke="var(--amber)" strokeWidth={1.4}
          opacity={0.45} style={{ filter: "drop-shadow(0 0 6px var(--amber))", pointerEvents: "none" }} />
      )}

      {/* 橋接節點 + 病灶 + 名字(主題常駐;其餘隨手出;邊界自動翻邊不切) */}
      {bridges.map(br => {
        const n = br.node, c = curById.get(n.id)!, on = hover === n.id, sel = selected === n.id;
        const showLabel = on || sel || (!focusId && ((mode === "axis" && n.type === "theme") || mode === "chain"));
        const base = 1;   // 整具骨所有點都在;calm 與 axis 的差別只在「名字綻不綻放」
        const dg = viz.diag?.[n.id] ?? [];
        const over = dg.includes("overloaded"), orphan = dg.includes("orphan"), hollow = dg.includes("hollow");
        const endSide = c.x > X1 - 150;                  // 靠右緣 → 標籤往左,避免切到
        return (
          <g key={n.id} transform={`translate(${c.x},${c.y})`} opacity={base * dim(n.id)}
            style={{ cursor: "pointer", transition: "opacity .25s ease" }}
            onMouseEnter={() => onHover(n.id)} onMouseLeave={() => onHover(null)}
            onClick={e => { e.stopPropagation(); onSelect(sel ? null : n.id); }}>
            {over && <circle className="diag-pulse" r={r(n) + 10} fill={DIAG.over} />}
            {orphan && <circle r={r(n) + 6} fill="none" stroke={DIAG.orphan} strokeWidth={1.3} strokeDasharray="3 3" opacity={0.85} />}
            {(on || sel) && <circle r={r(n) + (sel ? 10 : 7)} fill="none" stroke={COLOR[n.type]} strokeWidth={sel ? 1.6 : 1.2} opacity={sel ? 0.75 : 0.5} />}
            <circle r={r(n) * (on || sel ? 1.35 : 1)} fill={COLOR[n.type]} fillOpacity={hollow ? 0.28 : 1}
              style={{ transition: "r .2s ease", filter: on || sel || n.type === "theme" ? `drop-shadow(0 0 ${sel ? 11 : 7}px ${COLOR[n.type]})` : undefined }} />
            {hollow && <circle r={r(n)} fill="none" stroke={COLOR[n.type]} strokeWidth={1} opacity={0.7} />}
            {showLabel && (
              <text x={endSide ? -(r(n) + 6) : r(n) + 6} y={4} fontSize={on || sel ? 13.5 : 12}
                textAnchor={endSide ? "end" : "start"} fill={on || sel ? "#f6efd9" : "#d6cba6"} style={HALO}>
                {trunc(n.label)}{dg.length > 0 && <tspan fill={over ? DIAG.over : orphan ? DIAG.orphan : "#b9a88a"}> ⚑</tspan>}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
