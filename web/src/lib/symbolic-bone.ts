import type { Pt } from "./spline";

// 象徵骨:一副寫死的座標,只給「還沒有故事」的場合用(擲入框裡的淡虛線骨)。
// 那裡沒有資料可驅動——故事根本還不存在——所以象徵是誠實的。
// **不可用於孕育中的星**:那時這篇已經存在,拿假骨冒充它的骨架就是裝飾假裝資料
//(孕育第一段畫的是 CloudCollapse,analyst 交件後直接換真骨)。
export const SP: Pt[] = [[18, 98], [70, 66], [120, 118], [170, 72], [214, 112], [262, 80], [292, 100]];

export type SymbolicRib = { x: number; y: number; ex: number; ey: number; r: number; gold: boolean };

function onPoly(p: Pt[], f: number) {
  const seg = f * (p.length - 1);
  const i = Math.min(p.length - 2, Math.floor(seg));
  const t = seg - i;
  const [x1, y1] = p[i], [x2, y2] = p[i + 1];
  let tx = x2 - x1, ty = y2 - y1; const l = Math.hypot(tx, ty) || 1; tx /= l; ty /= l;
  return { x: x1 + (x2 - x1) * t, y: y1 + (y2 - y1) * t, nx: -ty, ny: tx };
}

export function buildRibs(): SymbolicRib[] {
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
