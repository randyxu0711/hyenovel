import rough from "roughjs";
import type { Options } from "roughjs/bin/core";
import { expand, GROUPS, hash, type FigureSpec, type Fill, type Group, type Pt } from "./poses";

export type Stroke = { d: string; stroke: string; width: number; fill: string };
export type Drawn = { groups: [Group, Stroke[]][]; eyes: Stroke[][]; lips: Stroke[]; mouth: Stroke[]; think: Stroke[][]; react: Stroke[] };

const ORDER: Group[] = ["legs", "tail", "body", "ears", "face"];
const INK: Record<Fill, string> = { main: "var(--fig-main)", second: "var(--fig-second)", lead: "var(--fig-lead)", none: "none" };
const VIEW_W = 120;
const gen = rough.generator();
const cache = new Map<string, Drawn>();

export const SMALL = 32;

function strokes(d: ReturnType<typeof gen.path>): Stroke[] {
  return d.sets.map(set => {
    const path = gen.opsToPath(set, 2);
    if (set.type === "fillPath") return { d: path, stroke: "none", width: 0, fill: d.options.fill ?? "none" };
    if (set.type === "fillSketch") return { d: path, stroke: d.options.fill ?? "none", width: d.options.fillWeight, fill: "none" };
    return { d: path, stroke: d.options.stroke, width: d.options.strokeWidth, fill: "none" };
  });
}

export function draw(spec: FigureSpec, size: number, seed: string, variant = 0): Drawn {
  const key = `${seed}|${size}|${variant}|${JSON.stringify(spec)}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const small = size <= SMALL;
  const u = VIEW_W / size;
  const sw = (size >= 80 ? 1.3 : size >= 40 ? 1.1 : 0.9) * u;
  let s = hash(seed) % 100000 + variant * 9973;
  const o = (extra: Options): Options => ({
    seed: ++s, roughness: 1.1, bowing: 0.8, stroke: INK.lead, strokeWidth: sw, hachureAngle: -41,
    hachureGap: 2.6 * u, fillWeight: 0.85 * u, fillStyle: small ? "solid" : "hachure", ...extra,
  });
  const { parts, eyes, mouth } = expand(spec);
  const byGroup = new Map<Group, Stroke[]>(GROUPS.map(g => [g, []]));
  for (const p of parts) {
    if (small && p.detail) continue;
    const fill = p.fill === "none" ? undefined : INK[p.fill];
    const solid = p.fill === "lead" || p.line === false;
    byGroup.get(p.group)!.push(...strokes(gen.path(p.d, o({
      fill, ...(solid && { fillStyle: "solid" }), stroke: p.line === false ? "none" : INK.lead,
    }))));
  }
  const eye = ([x, y]: Pt) => strokes(gen.circle(x, y, small ? 7 : 4.4, o({ fill: INK.lead, fillStyle: "solid", strokeWidth: sw * 0.5, roughness: 0.4 })));
  const [a, b, c] = mouth;
  const ex = (eyes[0][0] + eyes[1][0]) / 2, ey = Math.min(eyes[0][1], eyes[1][1]);
  const clamp = (v: number, hi: number) => Math.max(4, Math.min(hi, v));
  const think = [[16, -10, 3.5], [23, -18, 4.5], [31, -28, 6]].map(([dx, dy, r]) =>
    strokes(gen.circle(clamp(ex + dx, 114), clamp(ey + dy, 96), r, o({ strokeWidth: sw * 0.8 }))));
  const react = [[-12, -12, -17, -19], [0, -15, 0, -23], [12, -12, 17, -19]].flatMap(([x1, y1, x2, y2]) =>
    strokes(gen.line(clamp(ex + x1, 116), clamp(ey + y1, 96), clamp(ex + x2, 116), clamp(ey + y2, 96), o({ strokeWidth: sw * 1.1 }))));
  const out: Drawn = {
    groups: ORDER.map(g => [g, byGroup.get(g)!]),
    eyes: eyes.map(eye),
    lips: strokes(gen.curve([a, b, c], o({ strokeWidth: sw * 0.8 }))),
    mouth: strokes(gen.ellipse(b[0], (a[1] + b[1]) / 2 + 1, 7, 5, o({ fill: INK.lead, fillStyle: "solid", strokeWidth: sw * 0.6 }))),
    think, react,
  };
  if (cache.size > 300) cache.clear();
  cache.set(key, out);
  return out;
}
