import type { Lang } from "./i18n";

const grouped = new Intl.NumberFormat("en-US");

export function fmtTokens(n: number, lang: Lang): string {
  return lang === "zh-Hant" && n >= 10000 ? `${(n / 10000).toFixed(1)} 萬` : grouped.format(n);
}

export const fmtPct = (x: number): string => `${Math.round(x * 100)}%`;

export function fmtDelta(x: number): string {
  const pct = Math.round(Math.abs(x) * 100);
  return `${x < 0 && pct ? "−" : "+"}${pct}%`;
}

export const fmtSeconds = (ms: number): string => {
  const s = ms / 1000;
  return s >= 100 ? String(Math.round(s)) : s.toFixed(1);
};

const locale = (lang: Lang) => (lang === "en" ? "en" : "zh-Hant");

export const fmtTime = (unix: number, lang: Lang): string =>
  new Intl.DateTimeFormat(locale(lang), { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })
    .format(unix * 1000);

export const fmtDate = (unix: number, lang: Lang): string =>
  new Intl.DateTimeFormat(locale(lang), { month: "short", day: "numeric" }).format(unix * 1000);
