export const WORLD = { w: 2600, h: 1500 };
export type Stage = "overview" | "catalog" | "single";

const K: Record<Stage, number> = { overview: 0.9, catalog: 1.04, single: 1.5 };

export function fitScale(world: { w: number; h: number }, vw: number, vh: number): number {
  return Math.min(vw / world.w, vh / world.h);
}

export function zoomFor(stage: Stage, fit: number): number {
  return fit * K[stage];
}

export function camTransform(
  world: { w: number; h: number }, vw: number, vh: number, zoom: number,
  focus?: { x: number; y: number },
): { x: number; y: number; scale: number } {
  const cx = focus ? focus.x : world.w / 2;
  const cy = focus ? focus.y : world.h / 2;
  return { x: vw / 2 - cx * zoom, y: vh / 2 - cy * zoom, scale: zoom };
}

// 同心環佈局:中心留給種骨,故事繞著中心一圈圈排。
// 內圈先填滿再外擴;每圈容量隨半徑增加(圓周越長塞越多)。
// 橢圓(x 拉 RING_XSCALE)貼合世界/螢幕的寬高比 → y 是緊的維度。
// 未滿的環走 sparsePhase(新星先落地平線);滿環維持圈間錯開避免徑向連成直線。
const RING = { R0: 360, dR: 285, arc: 380 };
export const RING_XSCALE = 1.5;
const ringR = (ring: number) => RING.R0 + ring * RING.dR;
const ringCap = (ring: number) => Math.max(4, Math.round((2 * Math.PI * ringR(ring)) / RING.arc));

// 未滿環的相位:均分 occ 顆時,取「最小化 max|sin|」的旋轉最優解(y 緊,新星先落地平線)。
// 奇數 occ 的角度集 mod π 等距 π/occ,最優相位恰為 0;偶數為 0 或 π/occ,視 (occ-2)/2 奇偶
//(occ=4 → π/4 成 X 不成 +,與滿環 45° 錯開同理;test/camera-fit 以全相位掃描釘住最優性)。
export const sparsePhase = (occ: number): number =>
  occ % 2 ? 0 : ((occ - 2) / 2) % 2 ? Math.PI / occ : 0;

export function worldPos(i: number, world: { w: number; h: number }, total = i + 1): { x: number; y: number } {
  const cx = world.w / 2, cy = world.h / 2;
  let ring = 0, idx = i, start = 0;
  for (;;) {
    const cap = ringCap(ring);
    if (idx < cap) {
      const occ = Math.max(1, Math.min(cap, total - start)); // 這圈實際幾篇 → 均分整圈
      const R = ringR(ring);
      const base = occ === cap ? ring * 0.5 + Math.PI / 4 : sparsePhase(occ);
      const a = (idx / occ) * 2 * Math.PI + base;
      return { x: cx + Math.cos(a) * R * RING_XSCALE, y: cy + Math.sin(a) * R };
    }
    idx -= cap; start += cap; ring++;
  }
}

// 容納 count 篇需要的各圈半徑(給軌道線用,跟 worldPos 同源)
export function ringRadii(count: number): number[] {
  const rs: number[] = [];
  let acc = 0, ring = 0;
  while (acc < Math.max(1, count)) { rs.push(ringR(ring)); acc += ringCap(ring); ring++; }
  return rs;
}
