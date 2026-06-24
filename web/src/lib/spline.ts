export type Pt = [number, number];

export function beatsToPoints(values: number[], x0: number, x1: number, yBase: number, amp: number): Pt[] {
  const n = values.length;
  return values.map((v, i) => [x0 + ((x1 - x0) * i) / Math.max(1, n - 1), yBase - v * amp]);
}

export function spline(p: Pt[]): string {
  if (p.length === 0) return "";
  let d = `M${p[0][0]},${p[0][1]}`;
  for (let i = 0; i < p.length - 1; i++) {
    const p0 = p[i - 1] || p[i], p1 = p[i], p2 = p[i + 1], p3 = p[i + 2] || p2;
    const c1x = p1[0] + (p2[0] - p0[0]) / 6, c1y = p1[1] + (p2[1] - p0[1]) / 6;
    const c2x = p2[0] - (p3[0] - p1[0]) / 6, c2y = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C${c1x},${c1y} ${c2x},${c2y} ${p2[0]},${p2[1]}`;
  }
  return d;
}
