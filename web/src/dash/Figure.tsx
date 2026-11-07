import type { CSSProperties } from "react";
import type { Character } from "./api";
import { draw, type Drawn, type Stroke } from "./figure/draw";
import { fallback, PENS, type FigureSpec } from "./figure/poses";
import { useThemeState } from "./theme";

export type FigureState = "idle" | "reading" | "thinking" | "speaking" | "scanning" | "reacting";

const BOIL = 3;

const paths = (list: Stroke[]) => list.map((s, i) => (
  <path key={i} d={s.d} stroke={s.stroke} strokeWidth={s.width || undefined} fill={s.fill} />
));

function Lines({ drawn }: { drawn: Drawn }) {
  return (
    <>
      {drawn.groups.map(([group, list]) => list.length > 0 && <g key={group} className={group}>{paths(list)}</g>)}
      <g className="eyes">{drawn.eyes.map((e, i) => <g key={i} className="eye lid">{paths(e)}</g>)}</g>
      <g className="lips">{paths(drawn.lips)}</g>
      <g className="mouth">{paths(drawn.mouth)}</g>
      <g className="think">{drawn.think.map((d, i) => <g key={i}>{paths(d)}</g>)}</g>
      <g className="react">{paths(drawn.react)}</g>
    </>
  );
}

function drawable(spec: FigureSpec, size: number, seed: string): FigureSpec {
  try {
    draw(spec, size, seed);
    return spec;
  } catch {
    return fallback(seed);
  }
}

export default function Figure({ character, state = "idle", size = 32 }: { character: Character; state?: FigureState; size?: number }) {
  const { mode } = useThemeState();
  const seed = character.avatar.seed;
  const spec = drawable(character.figure ?? fallback(seed), size, seed);
  const variants = state === "speaking" ? BOIL : 1;
  const style = { "--fig-main": PENS[spec.main][mode], "--fig-second": PENS[spec.second][mode] } as CSSProperties;
  return (
    <svg className="fig" viewBox="0 0 120 100" width={size} height={Math.round(size * 100 / 120)} aria-hidden="true"
      data-who={character.id} data-state={state} data-tempo={spec.tempo ?? "mid"} data-move={spec.move}
      style={style} fill="none" strokeLinecap="round" strokeLinejoin="round">
      <g className="shape">
        {Array.from({ length: variants }, (_, v) => (
          <g key={v} className={`v v${v}`}><Lines drawn={draw(spec, size, seed, v)} /></g>
        ))}
      </g>
    </svg>
  );
}
