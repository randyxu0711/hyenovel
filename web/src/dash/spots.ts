export type Spot = { x: number; y: number; r: number };

/** 確定性的半色調斑點:n×n 方塊、格距 step;斑點範圍內的格點畫一顆小點,四邊環繞接縫。 */
export function spotField(n: number, step: number, seed: number): Spot[] {
  let s = seed;
  const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647;
  const blobs = Array.from({ length: 18 }, () => ({ x: rnd() * n, y: rnd() * n, r: 18 + rnd() * 30, k: 0.7 + rnd() * 0.5 }));
  const out: Spot[] = [];
  for (let y = step / 2; y < n; y += step) {
    for (let x = step / 2; x < n; x += step) {
      let f = 0;
      for (const b of blobs) {
        let dx = Math.abs(x - b.x), dy = Math.abs(y - b.y);
        dx = Math.min(dx, n - dx);
        dy = Math.min(dy, n - dy) / b.k;
        f = Math.max(f, 1 - Math.hypot(dx, dy) / b.r);
      }
      if (f > 0) out.push({ x, y, r: 0.6 + 1.5 * Math.min(1, f * 2.2) });
    }
  }
  return out;
}

/** 畫到 canvas 回 data URL(沒有 canvas 時回空字串)。 */
export function paintSpots(color: string): string {
  const N = 480;
  const c = document.createElement("canvas");
  c.width = c.height = N;
  const g = c.getContext("2d");
  if (!g) return "";
  g.fillStyle = color;
  for (const p of spotField(N, 8, 11)) { g.beginPath(); g.arc(p.x, p.y, p.r, 0, Math.PI * 2); g.fill(); }
  return c.toDataURL();
}
