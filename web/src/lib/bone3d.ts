export type V3 = [number, number, number];
export interface Bone3DRib { base: V3; tip: V3; theme: boolean; }
export interface Bone3D { spine: V3[]; ribs: Bone3DRib[]; }

function rng(seed: number) {
  let s = Math.abs(Math.floor(seed)) % 233280 || 7;
  return () => (s = (s * 9301 + 49297) % 233280) / 233280;
}

const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const scale = (a: V3, k: number): V3 => [a[0] * k, a[1] * k, a[2] * k];
const cross = (a: V3, b: V3): V3 =>
  [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a: V3): V3 => {
  const l = Math.hypot(a[0], a[1], a[2]) || 1;
  return [a[0] / l, a[1] / l, a[2] / l];
};
// Rodrigues:把向量 v 繞單位軸 k 轉 angle
function rotateAround(v: V3, k: V3, angle: number): V3 {
  const c = Math.cos(angle), s = Math.sin(angle);
  const kv = cross(k, v);
  const kk = k[0] * v[0] + k[1] * v[1] + k[2] * v[2];
  return [
    v[0] * c + kv[0] * s + k[0] * kk * (1 - c),
    v[1] * c + kv[1] * s + k[1] * kk * (1 - c),
    v[2] * c + kv[2] * s + k[2] * kk * (1 - c),
  ];
}

// 一具 3D 魚骨:tube 脊椎 + 繞脊椎四周岔開的肋籠 + 骨節端點。seed 決定骨形。
export function buildBone3D(seed: number, len = 6): Bone3D {
  const r = rng(seed);
  const n = 9;
  const ampY = 0.5 + r() * 0.7;
  const ampZ = 0.3 + r() * 0.5;
  const phY = r() * Math.PI * 2;
  const phZ = r() * Math.PI * 2;
  const freq = 1.2 + r() * 1.4;
  const spine: V3[] = Array.from({ length: n }, (_, i) => {
    const t = i / (n - 1);
    const x = -len / 2 + len * t;
    const y = Math.sin(phY + t * Math.PI * freq) * ampY * (0.5 + t * 0.6);
    const z = Math.cos(phZ + t * Math.PI * freq) * ampZ;
    return [x, y, z];
  });

  const m = 8 + Math.floor(r() * 5); // 8..12
  const ribs: Bone3DRib[] = [];
  for (let i = 0; i < m; i++) {
    const t = (i + 0.5) / m;
    const seg = t * (n - 1);
    const k = Math.min(n - 2, Math.floor(seg));
    const f = seg - k;
    const a = spine[k], b = spine[k + 1];
    const base = add(a, scale(sub(b, a), f));
    const tangent = norm(sub(b, a));
    // 基準法線(切線與世界 up 的叉積),再繞切線旋轉以在四周岔開
    let nrm = norm(cross(tangent, [0, 1, 0]));
    if (!isFinite(nrm[0])) nrm = [0, 0, 1];
    const splay = r() * Math.PI * 2;
    const dir = rotateAround(nrm, tangent, splay);
    const ribLen = 0.5 + (0.2 + r() * 0.78) * 1.8;
    const tip = add(base, scale(dir, ribLen));
    ribs.push({ base, tip, theme: r() > 0.8 });
  }
  return { spine, ribs };
}
