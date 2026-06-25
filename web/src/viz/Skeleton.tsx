import { buildBone } from "../lib/bone";
import type { VizData } from "../types";

// 星骨指紋:脊椎=張力曲線、肋=主題(上)/意象(下)、肋長=復現、亮節=主題。資料驅動,非裝飾。
export default function Skeleton({ viz, width }: { viz: VizData; width: number }) {
  const W = 310, H = 190;
  const { d, ribs } = buildBone(viz, W, H);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={width} height={(width * H) / W}
      style={{ filter: "drop-shadow(0 0 5px rgba(240,228,200,.3)) drop-shadow(0 0 18px rgba(214,196,150,.15))" }}>
      <path className="spine" d={d} pathLength={1} fill="none" stroke="var(--bone)" strokeWidth={2.2} strokeLinecap="round" />
      {ribs.map((b, i) => (
        <line key={`s${i}`} className="stub" x1={b.x1} y1={b.y1} x2={b.sx} y2={b.sy}
          stroke="#dccfae" strokeWidth={1.1} opacity={0.38} />
      ))}
      {ribs.map((b, i) => (
        <line key={`r${i}`} className="rib" pathLength={1} x1={b.x1} y1={b.y1} x2={b.x2} y2={b.y2}
          stroke="#dccfae" strokeWidth={1.1} strokeLinecap="round" opacity={0.76}>
          <title>{b.label}</title>
        </line>
      ))}
      {ribs.map((b, i) => (
        <circle key={`c${i}`} cx={b.cx} cy={b.cy} r={b.r} fill={b.theme ? "#ecc98a" : "#f3ead2"}>
          <title>{b.label}</title>
        </circle>
      ))}
    </svg>
  );
}
