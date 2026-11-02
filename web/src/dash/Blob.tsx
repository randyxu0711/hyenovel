import type { CSSProperties } from "react";
import type { Character } from "./api";
import { useThemeState } from "./theme";

export type BlobState = "idle" | "reading" | "scanning" | "speaking";

function hash(s: string): number {
  let h = 2166136261;
  for (const c of s) { h ^= c.codePointAt(0)!; h = Math.imul(h, 16777619); }
  return h >>> 0;
}

function rng(seed: number): () => number {
  let x = seed || 1;
  return () => { x ^= x << 13; x ^= x >>> 17; x ^= x << 5; return ((x >>> 0) % 10000) / 10000; };
}

const f = (n: number) => n.toFixed(2);

export function blobPath(seed: string): string {
  const r = rng(hash(seed)), n = 7, pts: [number, number][] = [];
  for (let i = 0; i < n; i++) {
    const a = Math.PI * 2 * i / n - Math.PI / 2, k = .82 + r() * .26;
    pts.push([50 + Math.cos(a) * 36 * k, 56 + Math.sin(a) * 34 * k]);
  }
  for (const p of pts) if (p[1] > 80) p[1] = 80 + (p[1] - 80) * .3;
  let d = `M${f(pts[0][0])},${f(pts[0][1])}`;
  for (let i = 0; i < n; i++) {
    const p0 = pts[(i - 1 + n) % n], p1 = pts[i], p2 = pts[(i + 1) % n], p3 = pts[(i + 2) % n];
    d += ` C${f(p1[0] + (p2[0] - p0[0]) / 6)},${f(p1[1] + (p2[1] - p0[1]) / 6)} ${f(p2[0] - (p3[0] - p1[0]) / 6)},${f(p2[1] - (p3[1] - p1[1]) / 6)} ${f(p2[0])},${f(p2[1])}`;
  }
  return d;
}

export default function Blob({ character, state = "idle", size = 32 }: { character: Character; state?: BlobState; size?: number }) {
  const { mode } = useThemeState();
  const style = { "--char": character.colors[mode].fill } as CSSProperties;
  return (
    <svg className="blob" viewBox="0 0 100 90" width={size} height={size * 0.9} aria-hidden="true" data-state={state} style={style}>
      <g className="shape">
        <path className="body" d={`${blobPath(character.id)}Z`} />
        <g className="eyes">
          <ellipse className="eye lid" cx="40" cy="50" rx="3.4" ry="4.2" />
          <ellipse className="eye lid" cx="60" cy="50" rx="3.4" ry="4.2" />
        </g>
        <path className="mouth" d="M45 62q5 4 10 0" />
      </g>
    </svg>
  );
}
