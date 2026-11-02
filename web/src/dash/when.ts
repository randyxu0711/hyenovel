import { translate, type Lang } from "./i18n";

const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();

/** 書架上的時間字(秒):今天 / 昨天 / N 天前(2–6)/ M/D(跨年加年)。日界用本地時區。 */
export function whenLabel(ts: number, now: number, lang: Lang): string {
  const d = new Date(ts * 1000), n = new Date(now * 1000);
  const diff = Math.round((day(n) - day(d)) / 86_400_000);
  if (diff <= 0) return translate(lang, "when.today");
  if (diff === 1) return translate(lang, "when.yesterday");
  if (diff <= 6) return translate(lang, "when.days", { n: diff });
  const md = `${d.getMonth() + 1}/${d.getDate()}`;
  return d.getFullYear() === n.getFullYear() ? md : `${d.getFullYear()}/${md}`;
}
