import { useMemo } from "react";
import { spline, type Pt } from "../lib/spline";

const W = 310, H = 190;
// 象徵性脊椎:孕育途中還沒真資料,先給一根有起伏的骨(誕生後由 Catalog 換成真實 Skeleton)
export const SP: Pt[] = [[18, 98], [70, 66], [120, 118], [170, 72], [214, 112], [262, 80], [292, 100]];

type Rib = { x: number; y: number; ex: number; ey: number; r: number; gold: boolean };

function onPoly(p: Pt[], f: number) {
  const seg = f * (p.length - 1);
  const i = Math.min(p.length - 2, Math.floor(seg));
  const t = seg - i;
  const [x1, y1] = p[i], [x2, y2] = p[i + 1];
  let tx = x2 - x1, ty = y2 - y1; const l = Math.hypot(tx, ty) || 1; tx /= l; ty /= l;
  return { x: x1 + (x2 - x1) * t, y: y1 + (y2 - y1) * t, nx: -ty, ny: tx };
}

export function buildRibs(): Rib[] {
  const specs = [
    { f: .12, up: true, gold: true, len: 38 }, { f: .22, up: false, gold: false, len: 26 },
    { f: .34, up: true, gold: false, len: 30 }, { f: .44, up: false, gold: true, len: 46 },
    { f: .55, up: true, gold: false, len: 34 }, { f: .66, up: false, gold: false, len: 24 },
    { f: .76, up: true, gold: true, len: 42 }, { f: .85, up: false, gold: false, len: 28 },
    { f: .93, up: true, gold: false, len: 30 },
  ];
  return specs.map(s => {
    const o = onPoly(SP, s.f);
    let nx = o.nx, ny = o.ny;
    if (s.up ? ny > 0 : ny < 0) { nx = -nx; ny = -ny; }   // 主題朝上、意象朝下
    return { x: o.x, y: o.y, ex: o.x + nx * s.len, ey: o.y + ny * s.len, r: s.gold ? 4 : 2.6, gold: s.gold };
  });
}

// 孕育星:吃 step 畫象徵骨。step1 脊椎、2 肋、3 節點、4 點亮。
// 已達成段落永久留著;正在做的前緣由 CSS(data-step)給呼吸流光,表示還在幹活但未完成。
export default function GestatingStar({ step, width = 300 }: { step: number; width?: number }) {
  const d = useMemo(() => spline(SP), []);
  const ribs = useMemo(buildRibs, []);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={width} height={(width * H) / W}
      className={`gs${step >= 4 ? " lit" : ""}`} data-step={step} data-testid="gestating"
      style={{ filter: "drop-shadow(0 0 6px rgba(240,228,200,.32)) drop-shadow(0 0 20px rgba(214,196,150,.16))" }}>
      <path className="gs-spine" d={d} pathLength={1} fill="none" stroke="var(--bone)"
        strokeWidth={2.2} strokeLinecap="round" style={{ strokeDashoffset: step >= 1 ? 0 : 1 }} />
      {ribs.map((b, i) => (
        <line key={`r${i}`} className="gs-rib" x1={b.x} y1={b.y} x2={b.ex} y2={b.ey} pathLength={1}
          stroke="#dccfae" strokeWidth={1.1} strokeLinecap="round"
          style={{ strokeDashoffset: step >= 2 ? 0 : 1, opacity: step >= 2 ? 0.76 : 0, transitionDelay: `${i * 0.1}s` }} />
      ))}
      {ribs.map((b, i) => (
        <circle key={`c${i}`} className="gs-node" cx={b.ex} cy={b.ey} r={step >= 3 ? b.r : 0}
          fill={b.gold ? "#ecc98a" : "#f3ead2"} style={{ transitionDelay: `${0.2 + i * 0.1}s` }} />
      ))}
      {/* 進度光點:孕育中沿脊椎頭→尾巡遊,到成形(step4)才熄 */}
      {step >= 1 && step < 4 && (
        <circle className="gs-spark" r={3.2} fill="#f8f0d8" opacity={0}>
          <animateMotion dur="2.2s" repeatCount="indefinite" path={d} />
          <animate attributeName="opacity" dur="2.2s" repeatCount="indefinite"
            values="0;1;1;0" keyTimes="0;0.12;0.85;1" />
        </circle>
      )}
    </svg>
  );
}
