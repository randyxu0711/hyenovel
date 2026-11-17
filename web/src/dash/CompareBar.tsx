import { useEffect, useRef } from "react";
import Icon from "./Icon";
import { useLang, useT } from "./i18n";
import type { CompareState } from "./useCompare";
import { whenLabel } from "./when";

/** 對照中取代版本條:舊版籤(可換)+ 新版籤、‹ n/m ›、只看新版、結束對照。 */
export default function CompareBar({ c, history }: { c: CompareState; history: { n: number; at: number }[] }) {
  const t = useT();
  const lang = useLang();
  const listRef = useRef<HTMLUListElement>(null);
  const { picker, setPicker } = c;
  useEffect(() => {
    if (!picker) return;
    listRef.current?.querySelector("button")?.focus();
    const onDown = (e: MouseEvent) => {
      const el = e.target as Element;
      if (!listRef.current?.contains(el) && !el.closest?.(".cmp-old")) setPicker(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [picker, setPicker]);
  const d = c.data;
  const n = d?.hunks.length ?? 0;
  return (
    <>
      {d && (
        <div className="paper-vers cmp-vers" role="group" aria-label={t("paper.versions")}>
          <div className="paper-seg">
            <button type="button" className="paper-v cmp-old" aria-label={t("compare.pickOld")} title={t("compare.pickOld")}
              aria-expanded={picker} onClick={() => setPicker(!picker)}>v{d.old}<span className="cmp-caret" aria-hidden="true">▾</span></button>
            <span className="paper-v cmp-new" aria-current="true">v{d.new}</span>
          </div>
          {picker && (
            <ul className="dash-float paper-vlist" role="dialog" aria-label={t("compare.pickOld")} ref={listRef}>
              {d.olds.map(o => (
                <li key={o.n}><button type="button" aria-current={o.n === d.old || undefined} onClick={() => c.pickOld(o.n)}>
                  <span>v{o.n}</span><span className="vdot-when">{whenLabel(history.find(h => h.n === o.n)?.at ?? 0, Date.now() / 1000, lang)}</span>
                </button></li>
              ))}
            </ul>
          )}
        </div>
      )}
      {d && (d.same ? <span className="paper-state cmp-same">{t("compare.same", { n: d.old })}</span> : (
        <span className="cmp-nav">
          <button type="button" className="ib" aria-label={t("compare.prev")} title={t("compare.prev")} onClick={() => c.step(-1)}><Icon name="prev" /></button>
          <span className="cmp-count">{c.hunk === null ? t("compare.total", { n }) : t("compare.count", { i: c.hunk + 1, n })}</span>
          <button type="button" className="ib" aria-label={t("compare.next")} title={t("compare.next")} onClick={() => c.step(1)}><Icon name="next" /></button>
        </span>
      ))}
      {d && !d.same && (
        <button type="button" className="ib" aria-pressed={c.clean} aria-label={t("compare.clean")} title={t("compare.clean")}
          onClick={() => c.setClean(!c.clean)}><Icon name="clean" /></button>
      )}
      <button type="button" className="ib cmp-toggle" aria-pressed="true" aria-label={t("compare.close")} title={t("compare.close")}
        onClick={c.toggle}><Icon name="compare" /></button>
    </>
  );
}
