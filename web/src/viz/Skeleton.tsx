import { buildBone } from "../lib/bone";
import type { VizData } from "../types";

const CX = 155, CY = 95; // buildBone 用 W=310,H=190 的中心

// 星骨指紋:脊椎=張力曲線、肋=主題(上)/意象(下)、肋長=復現、亮節=主題。資料驅動,非裝飾。
// burst=true:飛抵中心後,每個零件朝外(離中心的方向)爆散(見 journey.css 的 .skel.burst)。
// reassemble=true:burst 的逆放——零件從四周(--bx/--by)聚回、脊椎連線,重組成骨架(.skel.reassemble)。
export default function Skeleton({ viz, width, burst, reassemble }: { viz: VizData; width: number; burst?: boolean; reassemble?: boolean }) {
  const W = 310, H = 190;
  const { d, ribs } = buildBone(viz, W, H);
  const shard = (x: number, y: number) =>
    ({ ["--bx"]: `${((x - CX) * 2.6).toFixed(0)}px`, ["--by"]: `${((y - CY) * 2.6).toFixed(0)}px` } as React.CSSProperties);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={width} height={(width * H) / W}
      className={burst ? "skel burst" : reassemble ? "skel reassemble" : "skel"}
      style={{ filter: "drop-shadow(0 0 5px rgba(240,228,200,.3)) drop-shadow(0 0 18px rgba(214,196,150,.15))" }}>
      <path className="spine" d={d} pathLength={1} fill="none" stroke="var(--bone)" strokeWidth={2.2} strokeLinecap="round" />
      {ribs.map((b, i) => (
        <line key={`s${i}`} className="stub" x1={b.x1} y1={b.y1} x2={b.sx} y2={b.sy}
          stroke="#dccfae" strokeWidth={1.1} opacity={0.38} />
      ))}
      {ribs.map((b, i) => (
        <line key={`r${i}`} className="rib" pathLength={1} x1={b.x1} y1={b.y1} x2={b.x2} y2={b.y2}
          stroke="#dccfae" strokeWidth={1.1} strokeLinecap="round" opacity={0.76} style={shard(b.x2, b.y2)}>
          <title>{b.label}</title>
        </line>
      ))}
      {ribs.map((b, i) => (
        <circle key={`c${i}`} className="node" cx={b.cx} cy={b.cy} r={b.r} fill={b.theme ? "#ecc98a" : "#f3ead2"} style={shard(b.cx, b.cy)}>
          <title>{b.label}</title>
        </circle>
      ))}
    </svg>
  );
}
