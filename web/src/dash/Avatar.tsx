import type { CSSProperties } from "react";
import type { Character } from "./api";
import { localized, useLang } from "./i18n";
import { useThemeState } from "./theme";

const F = "var(--c-fill)";
const INK = "var(--dash-paper-ink)";
const INK2 = "var(--dash-paper-ink-2)";
const MUZZLE = "var(--dash-muzzle)";
const PAPER = "var(--dash-paper)";

// 畫法取自草圖的 <symbol>:毛色吃角色的 --c-fill,五官墨色與口鼻吃主題 token。
const FACES: Record<string, () => JSX.Element> = {
  hyena: () => (
    <>
      <path d="M22 13l3-6 3 5 3-6 3 6 3-5 3 6" fill="none" stroke={INK} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <ellipse cx="15" cy="20" rx="7" ry="9" fill={F} /><ellipse cx="49" cy="20" rx="7" ry="9" fill={F} />
      <ellipse cx="15" cy="21" rx="3.4" ry="5" fill={INK} opacity=".55" /><ellipse cx="49" cy="21" rx="3.4" ry="5" fill={INK} opacity=".55" />
      <circle cx="32" cy="35" r="20" fill={F} />
      <circle cx="19" cy="31" r="2.6" fill={INK} opacity=".5" /><circle cx="45" cy="28" r="2.2" fill={INK} opacity=".5" />
      <circle cx="42" cy="44" r="2.4" fill={INK} opacity=".45" /><circle cx="23" cy="45" r="1.8" fill={INK} opacity=".45" />
      <ellipse cx="32" cy="44" rx="10" ry="8" fill={MUZZLE} />
      <ellipse cx="32" cy="40" rx="4.4" ry="3" fill={INK} />
      <path d="M27 47q5 4 10 0" fill="none" stroke={INK} strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="25" cy="32" r="2.4" fill={INK} /><circle cx="39" cy="32" r="2.4" fill={INK} />
    </>
  ),
  buffalo: () => (
    <>
      <path d="M17 24C7 22 4 14 7 8c2 6 7 9 13 9M47 24c10-2 13-10 10-16-2 6-7 9-13 9" fill={INK2} />
      <ellipse cx="11" cy="29" rx="6" ry="3.6" fill={F} transform="rotate(-18 11 29)" />
      <ellipse cx="53" cy="29" rx="6" ry="3.6" fill={F} transform="rotate(18 53 29)" />
      <rect x="14" y="17" width="36" height="38" rx="17" fill={F} />
      <ellipse cx="32" cy="47" rx="13" ry="8.5" fill={MUZZLE} />
      <ellipse cx="27" cy="47" rx="2" ry="2.6" fill={INK} /><ellipse cx="37" cy="47" rx="2" ry="2.6" fill={INK} />
      <circle cx="24" cy="32" r="2.4" fill={PAPER} /><circle cx="40" cy="32" r="2.4" fill={PAPER} />
      <circle cx="24" cy="32" r="1.2" fill={INK} /><circle cx="40" cy="32" r="1.2" fill={INK} />
    </>
  ),
  deer: () => (
    <>
      <path d="M24 16l-4-9m4 9l-8-3m4-6l-3-3M40 16l4-9m-4 9l8-3m-4-6l3-3" stroke={INK2} strokeWidth="2.4" strokeLinecap="round" fill="none" />
      <ellipse cx="14" cy="25" rx="8" ry="4.4" fill={F} transform="rotate(-22 14 25)" />
      <ellipse cx="50" cy="25" rx="8" ry="4.4" fill={F} transform="rotate(22 50 25)" />
      <path d="M32 15c11 0 17 9 15 20-2 10-8 19-15 19s-13-9-15-19c-2-11 4-20 15-20z" fill={F} />
      <circle cx="28" cy="22" r="1.5" fill={MUZZLE} /><circle cx="35" cy="20" r="1.3" fill={MUZZLE} /><circle cx="33" cy="25" r="1.1" fill={MUZZLE} />
      <ellipse cx="32" cy="47" rx="7" ry="6" fill={MUZZLE} />
      <ellipse cx="32" cy="45" rx="3" ry="2.2" fill={INK} />
      <path d="M23 34q2 2 4 0M37 34q2 2 4 0" fill="none" stroke={INK} strokeWidth="2" strokeLinecap="round" />
    </>
  ),
};

/** 角色頭像。毛色/文字色來自角色資料(依目前晝夜);未知 kind 畫帶名字首字的圓。
 *  avatar.seed 先傳進來,第 1 批用不到。 */
export default function Avatar({ character, size = 32 }: { character: Character; size?: number }) {
  const { mode } = useThemeState();
  const lang = useLang();
  const c = character.colors[mode];
  const vars = { "--c-fill": c.fill, "--c-text": c.text } as CSSProperties;
  const Face = FACES[character.avatar.kind];
  if (!Face) {
    const initial = Array.from(localized(character.name, lang))[0] ?? "?";
    return (
      <span className="avatar avatar-fallback" data-kind={character.avatar.kind} aria-hidden="true"
        style={{ ...vars, width: size, height: size, fontSize: size * 0.5 /* t-ok: 隨頭像尺寸縮放 */ }}>
        {initial}
      </span>
    );
  }
  return (
    <svg className="avatar" viewBox="0 0 64 64" width={size} height={size} aria-hidden="true"
      data-kind={character.avatar.kind} style={vars}>
      <Face />
    </svg>
  );
}
