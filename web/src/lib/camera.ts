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

// 確定性散布:黃金角螺旋,讓多篇星骨在世界裡散得開又穩定
export function worldPos(i: number, world: { w: number; h: number }): { x: number; y: number } {
  const golden = 2.399963229;
  const a = i * golden;
  const r = 130 * Math.sqrt(i + 0.6);
  return { x: world.w / 2 + Math.cos(a) * r * 1.5, y: world.h / 2 + Math.sin(a) * r };
}
