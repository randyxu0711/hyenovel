import type { CSSProperties } from "react";
import type { Span, WorkMap } from "./api";
import { errorMessage, useLang, useT } from "./i18n";
import { useLinks } from "./links";
import type { Mark } from "./Paper";
import { useThemeState } from "./theme";
import { useCharacters } from "./useCharacters";

type Beat = WorkMap["beats"][number];

const DOTS = 10;
const inside = (s: Span | null, at: number | null): boolean =>
  !!s && s.start !== null && s.end !== null && at !== null && s.start <= at && at < s.end;

/** 結構圖分頁:點陣張力(每欄一個節拍、10 顆點)+ 意象出現在哪幾段。 */
export default function ChartTab({ map, marks, error = null }: { map: WorkMap | null; marks: Mark[]; error?: string | null }) {
  const t = useT();
  const lang = useLang();
  if (!map && error) return <p className="side-lede" role="alert">{t(errorMessage(error))}</p>;
  if (!map) return <p className="side-lede">{t("loading")}</p>;
  if (map.analysis_version === null) return <p className="side-lede">{t("chart.none")}</p>;

  const sep = lang === "en" ? ", " : "、";
  return (
    <div className="side-col">
      {map.analysis_version !== map.version && <p className="side-old">{t("chart.old", { n: map.analysis_version })}</p>}
      <p className="side-lede">{t("chart.lede")}</p>
      <Matrix beats={map.beats} marks={marks} />
      {map.motifs.length > 0 && <p className="side-kind">{t("chart.motifs")}</p>}
      {map.motifs.map(mo => {
        const at = [...new Set(mo.spans.flatMap(s => {
          const i = map.beats.findIndex(b => inside(b.span, s.start));
          return i < 0 ? [] : [i + 1];
        }))].sort((x, y) => x - y);
        return (
          <section key={mo.id} className="side-note">
            <h3>{mo.label}</h3>
            <p>{at.length ? t("chart.motifIn", { list: at.join(sep) }) : t("chart.motifNowhere")}</p>
          </section>
        );
      })}
    </div>
  );
}

/** 點陣張力:每欄一個節拍、10 顆點,點一欄稿捲到那個節拍。結構圖分頁與印字頭共用。
 *  print = 印字頭在印:欄一欄一欄出現(CSS 依 --dash-col 錯開)。 */
export function Matrix({ beats, marks, print = false }: { beats: Beat[]; marks: Mark[]; print?: boolean }) {
  const t = useT();
  const chars = useCharacters();
  const { mode } = useThemeState();
  const { jumpToPaper } = useLinks();
  const lit = beats.map(b => Math.round((b.intensity ?? 0) * DOTS));
  const peak = Math.max(0, ...lit) > 0 ? lit.indexOf(Math.max(...lit)) : -1;
  return (
    <div className={print ? "side-matrix is-print" : "side-matrix"} role="group" aria-label={t("chart.label")}
      style={{ gridTemplateColumns: `repeat(${beats.length}, minmax(0, 1fr))`, "--dash-cols": beats.length } as CSSProperties}>
      {beats.map((b, i) => {
        const span = b.span;
        // 欄底色點:最後一道起點落在這個節拍範圍內的痕跡
        const m = [...marks].reverse().find(x => inside(span, x.start));
        const who = m ? chars.byId(m.character) : null;
        return (
          <button key={b.id} type="button" className={i === peak ? "dash-mcol is-peak" : "dash-mcol"}
            disabled={!span || span.start === null} title={b.label}
            aria-label={t("chart.col", { n: i + 1, v: lit[i] })} style={{ "--dash-col": i } as CSSProperties}
            onClick={() => span && jumpToPaper(span)}>
            <span className="side-dots" aria-hidden="true">
              {Array.from({ length: DOTS }, (_, k) => (
                <i key={k} className={k < lit[i] ? "is-on" : undefined} style={{ "--dash-k": k } as CSSProperties} />
              ))}
            </span>
            <span className="dash-dm side-n">{i + 1}</span>
            {who && <span className="side-who" data-who={who.id} style={{ background: who.colors[mode].fill }} />}
          </button>
        );
      })}
    </div>
  );
}
