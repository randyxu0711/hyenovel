import { orderedBeats } from "./axis";
import { spline, type Pt } from "./spline";
import type { VizData, VizNode } from "../types";

export interface BoneRib {
  x1: number; y1: number; x2: number; y2: number; // 肋:從脊椎點往外(主題朝上、意象朝下)
  sx: number; sy: number;                          // 反向小 stub
  cx: number; cy: number; r: number;               // 骨節端點
  theme: boolean; label: string;                   // theme=true→琥珀大節;label=該主題/意象名
}
export interface Bone { d: string; ribs: BoneRib[]; pts: Pt[]; }

// 在脊椎折線上,求 x 處的 y 與單位切向(用來把肋沿法線岔出)
function onSpine(pts: Pt[], x: number): { y: number; tx: number; ty: number } {
  for (let i = 0; i < pts.length - 1; i++) {
    const [x1, y1] = pts[i], [x2, y2] = pts[i + 1];
    if (x >= x1 && x <= x2) {
      const t = (x - x1) / ((x2 - x1) || 1);
      let tx = x2 - x1, ty = y2 - y1; const tl = Math.hypot(tx, ty) || 1;
      return { y: y1 + (y2 - y1) * t, tx: tx / tl, ty: ty / tl };
    }
  }
  const last = pts[pts.length - 1];
  return { y: last[1], tx: 1, ty: 0 };
}

// 資料驅動的「星骨」指紋:脊椎=張力曲線、肋=主題(上)/意象(下)、肋長=復現次數。
export function buildBone(viz: VizData, w = 310, h = 190): Bone {
  const x0 = 18, x1 = w - 18, yMid = h / 2, amp = h * 0.34;

  // 脊椎 = 依 precedes 排序的 beat 張力;不足 2 拍給溫和預設,仍像一根骨。
  const beats = orderedBeats(viz);
  const vals = beats.length >= 2 ? beats.map(b => b.intensity ?? 0.4) : [0.4, 0.5, 0.4];
  const n = vals.length;
  const pts: Pt[] = vals.map((v, i) => [
    x0 + ((x1 - x0) * i) / Math.max(1, n - 1),
    yMid - (v - 0.5) * amp * 2, // 張力高→脊椎高(y 小)
  ]);
  const d = spline(pts);

  // 肋 = 主題 + 意象;沿原文出現位置 pos 落點,長度隨 evidence 數(復現)。
  const items = viz.nodes.filter((nd): nd is VizNode => nd.type === "theme" || nd.type === "motif");
  const recur = (nd: VizNode) => Math.max(1, nd.evidence.length);
  const maxRecur = Math.max(1, ...items.map(recur));

  const ribs: BoneRib[] = items.map((nd, i) => {
    const ev = nd.evidence.find(e => e.pos != null);
    const t = ev && ev.pos != null ? ev.pos : (i + 0.5) / items.length;
    const x = x0 + (x1 - x0) * t;
    const { y, tx, ty } = onSpine(pts, x);
    const theme = nd.type === "theme";
    // 法線;主題朝上(ny<0)、意象朝下(ny>0)
    let nx = -ty, ny = tx;
    if (theme ? ny > 0 : ny < 0) { nx = -nx; ny = -ny; }
    const len = 14 + (recur(nd) / maxRecur) * 56;
    return {
      x1: x, y1: y, x2: x + nx * len, y2: y + ny * len,
      sx: x - nx * 6, sy: y - ny * 6,
      cx: x + nx * len, cy: y + ny * len, r: theme ? 4 : 2.6,
      theme, label: nd.label,
    };
  });

  return { d, ribs, pts };
}
