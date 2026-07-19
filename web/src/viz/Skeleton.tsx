import { buildBone } from "../lib/bone";
import type { VizData } from "../types";

const CX = 155, CY = 95; // buildBone 用 W=310,H=190 的中心

// 星骨指紋:脊椎=張力曲線、肋=主題(上)/意象(下)、肋長=復現、亮節=主題。資料驅動,非裝飾。
// burst=true:飛抵中心後,每個零件朝外(離中心的方向)爆散(見 journey.css 的 .skel.burst)。
// reassemble=true:burst 的逆放——零件從四周(--bx/--by)聚回,重組成骨架(.skel.reassemble)。
// ignite=true:**誕生**——核心點火、骨從中心向外亮起(.skel.ignite)。
//   刻意不共用 reassemble:那是退場語言,前提是「碎片剛炸開、正在外面」。誕生的前提相反——
//   質量剛塌縮進核心(CloudCollapse),零件從沒去過外面;讓它們從四周飛回來,等於憑空多出一個
//   跟前一秒畫面矛盾的前提。天文上亦然:恆星在核心點火,不從外圍組裝。
// reading=true:**criticizer 跑中**(分鐘級)——一道光沿脊椎(=文本時間軸)掃過,
//   掃到哪根肋就把那個節點掂亮一下,掃完從頭再來(.skel.reading)。
//   每一層都是真的:脊椎 x 軸就是閱讀順序;肋的 x 來自 evidence.pos,即該意象/主題**在原文的
//   真實位置**(viz.py 的 locate 從 source.md 搜出來)→ **亮起的順序 = 讀者真的會遇到它們的順序**。
//   **循環而非進度條**:我們無從得知 criticizer 還要跑多久(同 CloudCollapse 的誠實邏輯)。
//   它不宣稱「此刻正在看第 3 個節點」,只宣稱「有人正在從頭到尾反覆讀這篇」——那是真的。
const IGNITE_SPAN = 0.34;   // 由核心到邊緣的錯開總長(秒),與 journey.css 的 ignite* 時長相稱
const NODE_LAG = 0.3;       // 節點等自己那根肋畫出去了才浮現
const READ_CYCLE = 4.4;     // 掃一趟的秒數,與 journey.css 的 readSweep/weigh 同值(靠這個永遠同步)
const X0 = 18;              // = buildBone 的左緣;肋的 t 靠它換算

// dormant=停拍(paused/failed 卡在 criticizer,骨已在):不點火不掃描 —— 靜止的骨,
//   顏色由 CSS(.skel.paused/.failed)接手(冷藍睡著 / 鏽紅熄火),故此時不給 inline 輝光免得蓋掉。
export default function Skeleton(
  { viz, width, burst, reassemble, ignite, reading, dormant }:
  { viz: VizData; width: number; burst?: boolean; reassemble?: boolean; ignite?: boolean;
    reading?: boolean; dormant?: "paused" | "failed" },
) {
  const W = 310, H = 190;
  const { d, ribs } = buildBone(viz, W, H);
  const shard = (x: number, y: number) =>
    ({ ["--bx"]: `${((x - CX) * 2.6).toFixed(0)}px`, ["--by"]: `${((y - CY) * 2.6).toFixed(0)}px` } as React.CSSProperties);
  // 點火錯開:離核心越遠越晚亮 —— 光從中心推出去,不是從外面收回來
  const fromCore = (x: number, lag = 0): React.CSSProperties =>
    (ignite ? { animationDelay: `${((Math.abs(x - CX) / (W / 2)) * IGNITE_SPAN + lag).toFixed(3)}s` } : {});
  // 掂量錯開:節點要**正好**在掃描光走到自己那根肋時亮,不然就成了各跑各的裝飾。
  // 兩處要補償:掃描段跑的是 pathLength 的 -.06→1(見 readSweep,總程 1.06),
  // 而 weigh 的閃光落在自己週期的 5%。與 readSweep 同週期 → 補一次,之後每趟都對得上。
  const readAt = (x: number): React.CSSProperties => {
    if (!reading) return {};
    const p = (x - X0) / (W - X0 * 2);        // 肋在脊椎上的相對位置 = 它在原文的相對位置
    return { animationDelay: `${(((p + 0.06) / 1.06 - 0.05) * READ_CYCLE).toFixed(2)}s` };
  };
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={width} height={(width * H) / W}
      className={`skel${burst ? " burst" : reassemble ? " reassemble" : ignite ? " ignite" : reading ? " reading" : dormant ? ` ${dormant}` : ""}`}
      style={dormant ? undefined : { filter: "drop-shadow(0 0 5px rgba(240,228,200,.3)) drop-shadow(0 0 18px rgba(214,196,150,.15))" }}>
      <path className="spine" d={d} pathLength={1} fill="none" stroke="var(--bone)" strokeWidth={2.2} strokeLinecap="round" />
      {/* 掃描光:同一條脊椎再描一次,只讓一小段亮著跑(dash 掃描,非 SMIL —— SMIL 不吃減動) */}
      {reading && <path className="read-sweep" d={d} pathLength={1} fill="none"
        stroke="#f8f0d8" strokeWidth={2.6} strokeLinecap="round" />}
      {ribs.map((b, i) => (
        <line key={`s${i}`} className="stub" x1={b.x1} y1={b.y1} x2={b.sx} y2={b.sy}
          stroke="#dccfae" strokeWidth={1.1} opacity={0.38} style={fromCore(b.x1)} />
      ))}
      {ribs.map((b, i) => (
        <line key={`r${i}`} className="rib" pathLength={1} x1={b.x1} y1={b.y1} x2={b.x2} y2={b.y2}
          stroke="#dccfae" strokeWidth={1.1} strokeLinecap="round" opacity={0.76}
          style={{ ...shard(b.x2, b.y2), ...fromCore(b.x1) }}>
          <title>{b.label}</title>
        </line>
      ))}
      {ribs.map((b, i) => (
        <circle key={`c${i}`} className="node" cx={b.cx} cy={b.cy} r={b.r} fill={b.theme ? "#ecc98a" : "#f3ead2"}
          style={{ ...shard(b.cx, b.cy), ...fromCore(b.x1, NODE_LAG), ...readAt(b.x1) }}>
          <title>{b.label}</title>
        </circle>
      ))}
    </svg>
  );
}
