export type Spot = { x: number; y: number; r: number };

/** 確定性的半色調斑點:n×n 方塊、格距 step;斑點範圍內的格點畫一顆小點,四邊環繞接縫。 */
export function spotField(n: number, step: number, seed: number, count = 18): Spot[] {
  let s = seed;
  const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647;
  const blobs = Array.from({ length: count }, () => ({ x: rnd() * n, y: rnd() * n, r: 18 + rnd() * 30, k: 0.7 + rnd() * 0.5 }));
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

export const SPOT_TILES = [{ n: 480, seed: 11, count: 10 }, { n: 624, seed: 23, count: 12 }] as const;

/** 兩張不同大小的方塊疊著鋪,週期拉長到看不出網格;回 CSS background-image 值(沒有 canvas 時回空字串)。 */
export function paintSpots(color: string): string {
  const urls: string[] = [];
  for (const { n, seed, count } of SPOT_TILES) {
    const c = document.createElement("canvas");
    c.width = c.height = n;
    const g = c.getContext("2d");
    if (!g) return "";
    g.fillStyle = color;
    for (const p of spotField(n, 8, seed, count)) { g.beginPath(); g.arc(p.x, p.y, p.r, 0, Math.PI * 2); g.fill(); }
    urls.push(`url(${c.toDataURL()})`);
  }
  return urls.join(", ");
}
