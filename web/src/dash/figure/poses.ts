import grammar from "./grammar.json";

export type Pen = keyof typeof grammar.pens;
export type Pose = "quad" | "perch" | "upright" | "frame" | "long" | "mound" | "wisp";
export type Group = "body" | "legs" | "face" | "ears" | "tail";
export type Fill = "main" | "second" | "lead" | "none";
export type Tempo = "slow" | "mid" | "quick";
export type Move = "tail-sway" | "tail-flick" | "ears-drift" | "ears-bob";
export type Pt = [number, number];
export type Part = { group: Group; d: string; fill: Fill; line?: boolean; detail?: boolean };
export type Face = { eyes: [Pt, Pt]; mouth: [Pt, Pt, Pt] };
export type FigureSpec = {
  pose?: Pose; parts: Part[]; eyes?: [Pt, Pt]; mouth?: [Pt, Pt, Pt]; main: Pen; second: Pen; tempo?: Tempo; move?: Move;
};

export const PENS = grammar.pens;
export const GROUPS = grammar.groups as Group[];

export const POSES = grammar.poses as unknown as Record<Pose, Face & { parts: Part[] }>;

const POSE_IDS = Object.keys(POSES) as Pose[];
const FALLBACK_PENS: Pen[] = ["apricot", "olive", "moss", "sand", "ochre", "rust", "rose", "plum", "slate"];

export function hash(s: string): number {
  let h = 2166136261;
  for (const c of s) { h ^= c.codePointAt(0)!; h = Math.imul(h, 16777619); }
  return h >>> 0;
}

export function fallback(seed: string): FigureSpec {
  const h = hash(seed);
  const main = FALLBACK_PENS[h % FALLBACK_PENS.length];
  return { pose: POSE_IDS[(h >>> 8) % POSE_IDS.length], parts: [], main, second: main === "bark" ? "bone" : "bark" };
}

export function expand(spec: FigureSpec): Face & { parts: Part[] } {
  const base = spec.pose ? POSES[spec.pose] : null;
  return {
    parts: [...(base?.parts ?? []), ...spec.parts],
    eyes: spec.eyes ?? base!.eyes,
    mouth: spec.mouth ?? base!.mouth,
  };
}
