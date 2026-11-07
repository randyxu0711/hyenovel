import type { ReactNode } from "react";

/** 圖示:路徑照第 2 輪草圖的 <symbol>。線寬、端點、顏色由 CSS `.ico` 決定(currentColor)。 */
const PATHS = {
  panel: <><rect x="2.5" y="3.5" width="13" height="11" rx="2" /><path d="M7 3.5v11" /></>,
  new: <><path d="M4 2.5h7l3 3v10H4z" /><path d="M9 8v5M6.5 10.5h5" /></>,
  find: <><circle cx="8" cy="8" r="4.6" /><path d="M11.5 11.5L15 15" /></>,
  gear: <><path d="M2.5 4.5h4.2M9.3 4.5h6.2M2.5 9h8.2M13.3 9h2.2M2.5 13.5h2.2M7.3 13.5h8.2" /><circle cx="8" cy="4.5" r="1.3" /><circle cx="12" cy="9" r="1.3" /><circle cx="6" cy="13.5" r="1.3" /></>,
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
  send: <><path d="M3 9.5L15 3.5 11.5 15 9 10z" /><path d="M9 10l6-6.5" /></>,
  stop: <rect x="5" y="5" width="8" height="8" rx="1.5" />,
  focus: <path d="M3 7V3h4M15 7V3h-4M3 11v4h4M15 11v4h-4" />,
  close: <path d="M5 5l8 8M13 5l-8 8" />,
  pause: <path d="M6.5 4v10M11.5 4v10" />,
  offTarget: <><circle cx="9" cy="9" r="6" /><path d="M4.8 13.2l8.4-8.4" /></>,
  down: <path d="M9 3v8M5.5 8L9 11.5 12.5 8M3.5 15h11" />,
  up: <path d="M9 12V4M5.5 7L9 3.5 12.5 7M3.5 15h11" />,
  swap: <path d="M3 6.5h10.5L11 4M15 11.5H4.5L7 14" />,
  memory: <path d="M5 2.5h8v13l-4-3-4 3z" />,
  copy: <><rect x="6.5" y="6.5" width="8.5" height="8.5" rx="1.5" /><path d="M11.5 3.5H4.5A1.5 1.5 0 0 0 3 5v6.5" /></>,
  edit: <path d="M3.5 14.5l.7-3L12 3.7a1.4 1.4 0 0 1 2 0l.3.3a1.4 1.4 0 0 1 0 2l-7.8 7.8z" />,
  flag: <><path d="M4.5 16V2.5" /><path d="M4.5 3h9l-2.2 3.2 2.2 3.3h-9" /></>,
  sheet2:<><path d="M6 2.5h6.5l2.5 2.5v10H6z" /><path d="M3 5v11.5h9" opacity=".55" /></>,
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof PATHS;
export const ICON_NAMES = Object.keys(PATHS) as IconName[];

export default function Icon({ name }: { name: IconName }) {
  return <svg className="ico" viewBox="0 0 18 18" width="18" height="18" aria-hidden="true">{PATHS[name]}</svg>;
}
