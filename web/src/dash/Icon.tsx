import type { ReactNode } from "react";

/** 圖示:路徑照第 2 輪草圖的 <symbol>。線寬、端點、顏色由 CSS `.ico` 決定(currentColor)。 */
const PATHS = {
  panel: <><rect x="2.5" y="3.5" width="13" height="11" rx="2" /><path d="M7 3.5v11" /></>,
  new: <><path d="M4 2.5h7l3 3v10H4z" /><path d="M9 8v5M6.5 10.5h5" /></>,
  find: <><circle cx="8" cy="8" r="4.6" /><path d="M11.5 11.5L15 15" /></>,
  gear: <><circle cx="9" cy="9" r="2.4" /><path d="M9 1.8v2M9 14.2v2M1.8 9h2M14.2 9h2M3.9 3.9l1.4 1.4M12.7 12.7l1.4 1.4M3.9 14.1l1.4-1.4M12.7 5.3l1.4-1.4" /></>,
  plus: <path d="M9 4v10M4 9h10" />,
  dots: <><circle cx="4.5" cy="9" r=".9" /><circle cx="9" cy="9" r=".9" /><circle cx="13.5" cy="9" r=".9" /></>,
  talk: <path d="M3 4.5h12v8H8l-3.5 3v-3H3z" />,
  back: <><path d="M7 5L3.5 8.5 7 12" /><path d="M3.5 8.5H11a3.5 3.5 0 0 1 0 7H9" /></>,
  look: <><circle cx="9" cy="9" r="6" /><path d="M9 3v12M3 9h12" opacity=".4" /></>,
  person: <><circle cx="9" cy="6.5" r="3" /><path d="M3.5 15.5c.8-3 3-4.5 5.5-4.5s4.7 1.5 5.5 4.5" /></>,
  box: <><path d="M2.5 5h13v3h-13zM3.5 8v7h11V8" /><path d="M7.5 11h3" /></>,
  auto: <><circle cx="9" cy="9" r="6" /><path d="M9 3a6 6 0 0 1 0 12z" fill="currentColor" stroke="none" /></>,
  sun: <><circle cx="9" cy="9" r="3.2" /><path d="M9 2v1.6M9 14.4V16M2 9h1.6M14.4 9H16M4 4l1.1 1.1M12.9 12.9L14 14M4 14l1.1-1.1M12.9 5.1L14 4" /></>,
  moon: <path d="M14.5 11.5A6 6 0 0 1 6.5 3.5a6 6 0 1 0 8 8z" />,
  hori: <path d="M3 5h12M3 9h12M3 13h8" />,
  vert: <path d="M13 3v12M9 3v12M5 3v8" />,
  stack: <><path d="M6 2.5h6.5l2.5 2.5v10H6z" /><path d="M3 5v11.5h9" opacity=".55" /><path d="M10.5 7.5v4M8.5 9.5h4" /></>,
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof PATHS;
export const ICON_NAMES = Object.keys(PATHS) as IconName[];

export default function Icon({ name }: { name: IconName }) {
  return <svg className="ico" viewBox="0 0 18 18" width="18" height="18" aria-hidden="true">{PATHS[name]}</svg>;
}
