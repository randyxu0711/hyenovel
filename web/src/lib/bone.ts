import { spline, type Pt } from "./spline";

export interface BoneRib {
  x1: number; y1: number; x2: number; y2: number; // 主肋(沿法線往外)
  sx: number; sy: number;                          // 反向小 stub 端
  cx: number; cy: number; r: number; theme: boolean; // 骨節端點
}
export interface Bone { d: string; ribs: BoneRib[]; }

function rng(seed: number) {
  let s = Math.abs(Math.floor(seed)) % 233280 || 7;
  return () => (s = (s * 9301 + 49297) % 233280) / 233280;
}

// v3 的「魚骨」骨架:有機脊椎 + 沿法線岔出的肋 + 端點。seed 決定,純裝飾(不編碼張力)。
export function buildBone(seed: number, w = 310, h = 190): Bone {
  const r = rng(seed);
  const x0 = 18, x1 = w - 18, yMid = h / 2;
  const n = 7;
  const amp = 16 + r() * 16;
  const phase = r() * Math.PI * 2;
  const freq = 1.3 + r() * 1.6;
  const pts: Pt[] = Array.from({ length: n }, (_, i) => {
    const t = i / (n - 1);
    return [x0 + (x1 - x0) * t, yMid + Math.sin(phase + t * Math.PI * freq) * amp * (0.55 + t * 0.5)];
  });
  const d = spline(pts);

  const m = 6 + Math.floor(r() * 4);
  const ribs: BoneRib[] = [];
  for (let i = 0; i < m; i++) {
    const t = (i + 0.5) / m;
    const seg = t * (n - 1);
    const k = Math.min(n - 2, Math.floor(seg));
    const f = seg - k;
    const a = pts[k], b = pts[k + 1];
    const px = a[0] + (b[0] - a[0]) * f, py = a[1] + (b[1] - a[1]) * f;
    let tx = b[0] - a[0], ty = b[1] - a[1];
    const tl = Math.hypot(tx, ty) || 1; tx /= tl; ty /= tl;
    let nx = -ty, ny = tx;           // 法線
    if (ny > 0) { nx = -nx; ny = -ny; } // 一律朝上岔出
    const len = 16 + (0.2 + r() * 0.78) * 64;
    const theme = r() > 0.78;
    ribs.push({
      x1: px, y1: py, x2: px + nx * len, y2: py + ny * len,
      sx: px - nx * 6, sy: py - ny * 6,
      cx: px + nx * len, cy: py + ny * len, r: theme ? 4 : 2.3, theme,
    });
  }
  return { d, ribs };
}
