import type { CSSProperties } from "react";
import type { Character } from "./api";
import { useThemeState } from "./theme";

const LINE = { fill: "none", stroke: "var(--c-text)", strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round" } as const;

// 線條動物圖示(viewBox 32):只畫輪廓,顏色吃角色的 --c-text;底與邊吃 --c-fill。
const ICONS: Record<string, () => JSX.Element> = {
  hyena: () => (
    <g {...LINE}>
      <path d="M8 14L8.5 6l5 3.6M24 14l-.5-8-5 3.6" />
      <path d="M8 14c0 8 5 12 8 12s8-4 8-12c0-3-4-5-8-5s-8 2-8 5z" />
      <path d="M12.5 16h.01M19.5 16h.01M14.5 20h3l-1.5 1.8z" />
    </g>
  ),
  buffalo: () => (
    <g {...LINE}>
      <path d="M9 12C4 11 3 7 5 4c1 3 3 5 6 5.4M23 12c5-1 6-5 4-8-1 3-3 5-6 5.4" />
      <path d="M9 11h14v8a7 7 0 0 1-14 0z" />
      <path d="M13 21h.01M19 21h.01M12.5 16h.01M19.5 16h.01" />
    </g>
  ),
  deer: () => (
    <g {...LINE}>
      <path d="M12 9L10 4M12 9L8 7M20 9l2-5M20 9l4-2" />
      <path d="M16 8c5 0 7 5 6 10-1 5-4 8-6 8s-5-3-6-8c-1-5 1-10 6-10z" />
      <path d="M13 16h.01M19 16h.01M15 21h2" />
    </g>
  ),
};
const GENERIC = () => (
  <g {...LINE}>
    <circle cx="16" cy="16" r="8" />
    <path d="M13 15h.01M19 15h.01M13.5 19.5q2.5 1.8 5 0" />
  </g>
);

/** 角色徽章:fill 色淡底、細邊、線條動物圖示。未知 kind 用通用圖示。 */
export default function Avatar({ character, size = 32 }: { character: Character; size?: number }) {
  const { mode } = useThemeState();
  const c = character.colors[mode];
  const vars = { "--c-fill": c.fill, "--c-text": c.text } as CSSProperties;
  const Icon = ICONS[character.avatar.kind] ?? GENERIC;
  return (
    <svg className="avatar" viewBox="0 0 32 32" width={size} height={size} aria-hidden="true"
      data-kind={character.avatar.kind} style={vars}>
      <circle cx="16" cy="16" r="15" style={{ fill: "color-mix(in srgb, var(--c-fill) 22%, var(--dash-desk))", stroke: "var(--c-fill)" }} strokeWidth="1" />
      <Icon />
    </svg>
  );
}
