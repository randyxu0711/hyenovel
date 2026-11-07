import type { CSSProperties } from "react";
import type { Span, WorkMap } from "./api";
import { errorMessage, useLang, useT } from "./i18n";
import { useLinks } from "./links";
import type { Mark } from "./Paper";

type Beat = WorkMap["beats"][number];

const DOTS = 10;
const inside = (s: Span | null, at: number | null): boolean =>
  !!s && s.start !== null && s.end !== null && at !== null && s.start <= at && at < s.end;

/** 結構圖分頁:張力曲線 + 意象出現在哪幾段。 */
export default function ChartTab({ map, marks, error = null, ob = null, onOb }: {
  map: WorkMap | null; marks: Mark[]; error?: string | null;
  /** 選中的觀察(意象 id):稿上它的引文畫鉛筆直線。 */
  ob?: string | null; onOb?: (id: string | null) => void;
}) {
  const t = useT();
  const lang = useLang();
  if (!map && error) return <p className="side-lede" role="alert">{t(errorMessage(error))}</p>;
  if (!map) return <p className="side-lede">{t("loading")}</p>;
  if (map.analysis_version === null) return <p className="side-lede">{t("chart.none")}</p>;

  const sep = lang === "en" ? ", " : "、";
  return (
    <div className="side-col">
      {map.analysis_version !== map.version && <p className="side-old">{t("chart.old", { n: map.analysis_version })}</p>}
      {map.drift && map.drift.lost > 0 && (
        <p className="side-old">{t("chart.drift", { lost: map.drift.lost, total: map.drift.total, n: map.version })}</p>
      )}
      {map.drift && map.drift.orphaned.length > 0 && (
        <>
          <p className="side-old">{t("chart.orphaned")}</p>
          <ul className="side-old">{map.drift.orphaned.map(o => <li key={o.id}>{o.label}</li>)}</ul>
        </>
      )}
      <Curve beats={map.beats} marks={marks} />
      {map.motifs.length > 0 && <p className="side-kind">{t("chart.motifs")}</p>}
      {map.motifs.map(mo => {
        const at = [...new Set(mo.spans.flatMap(s => {
          const i = map.beats.findIndex(b => inside(b.span, s.start));
          return i < 0 ? [] : [i + 1];
        }))].sort((x, y) => x - y);
        return (
          <button key={mo.id} type="button" className="side-ob" aria-pressed={ob === mo.id}
            disabled={!at.length} title={at.length ? undefined : t("chart.motifNowhere")}
            onClick={() => onOb?.(ob === mo.id ? null : mo.id)}>
            <span className="side-ob-name">{mo.label}</span>
            {at.length > 0 && <span className="side-ob-sub">{t("chart.motifIn", { list: at.join(sep) })}</span>}
          </button>
        );
      })}
    </div>
  );
}

const H = 60;

/** 張力曲線:鉛筆折線,一個節拍一欄可點的熱區;陪讀者提過的段在段號上畫波浪線。 */
export function Curve({ beats, marks }: { beats: Beat[]; marks: Mark[] }) {
  const t = useT();
  const { jumpToPaper } = useLinks();
  const lit = beats.map(b => Math.round((b.intensity ?? 0) * DOTS));
  const peak = Math.max(0, ...lit) > 0 ? lit.indexOf(Math.max(...lit)) : -1;
  const n = beats.length;
  const y = (v: number) => Math.round((1 - v / DOTS) * (H - 6) * 10) / 10 + 3;
  const pts = n === 1 ? `0,${y(lit[0])} 100,${y(lit[0])}`
    : lit.map((v, i) => `${Math.round((i + 0.5) / n * 1000) / 10},${y(v)}`).join(" ");
  return (
    <div className="side-curve" role="group" aria-label={t("chart.label")}
      style={{ "--dash-cols": n } as CSSProperties}>
      <svg className="side-line" viewBox={`0 0 100 ${H}`} preserveAspectRatio="none" aria-hidden="true">
        <polyline points={pts} />
      </svg>
      {beats.map((b, i) => {
        const span = b.span;
        const m = [...marks].reverse().find(x => inside(span, x.start));
        return (
          <button key={b.id} type="button" className={i === peak ? "dash-mcol is-peak" : "dash-mcol"}
            disabled={!span || span.start === null} title={b.label}
            aria-label={t("chart.col", { n: i + 1, v: lit[i] })}
            onClick={() => span && jumpToPaper(span)}>
            <span className="dash-dm side-n">{i + 1}</span>
            {m && (
              <svg className="side-wave" data-who={m.character} viewBox="0 0 14 4" aria-hidden="true">
                <path d="M0 2q1.75-2.4 3.5 0t3.5 0 3.5 0 3.5 0" />
              </svg>
            )}
          </button>
        );
      })}
    </div>
  );
}
