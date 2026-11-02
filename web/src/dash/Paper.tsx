import { Fragment, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { cpLength, cpSlice } from "./cp";
import { useT } from "./i18n";
import { useLinks } from "./links";
import { paginate, tcyRuns, type PageSeg, type Segment } from "./paginate";
import { usePaperFlow, type PaperFlow } from "./paperFlow";
import { useSelectionQuote } from "./useSelectionQuote";

/** 讀者在稿上的一道痕跡:位移是原文的 code point 索引(den 給的)。id = markId(...),同一道痕跡跨重繪不變。 */
export type Mark = { start: number; end: number; character: string; id: string };
/** 一筆畫上去的時間:CSS 動畫長度(--dash-draw)與畫線佇列每筆的停留都用它,佇列才不會把筆畫截斷。 */
export const DRAW_MS = 900;
export const markId = (start: number, end: number, character: string) => `${start}-${end}-${character}`;

/** 設定頁選的稿字級(小/中/大 = s/m/l),存 localStorage;沒存或值不認得 = 中。 */
export const PAPER_SIZE_KEY = "hyenovel.paperSize";
export type PaperSize = "s" | "m" | "l";
export function loadPaperSize(): PaperSize {
  try { const v = localStorage.getItem(PAPER_SIZE_KEY); return v === "s" || v === "l" ? v : "m"; } catch { return "m"; }
}

const FLASH_MS = 1400;
const last = <T,>(xs: T[]): T | undefined => xs[xs.length - 1];
/** 寬鬆比對用:去標點、符號、空白,NFKC。 */
export const bare = (s: string) => s.normalize("NFKC").replace(/[\p{P}\p{S}\s]/gu, "");

/** 原文分段(換行切),每段記它在原文的 code point 起點;段頭尾空白不算進段裡。
 *  第一段若只是標題(標點、全半形、空白不計)就略過,標題已經在頂列了。 */
export function segments(text: string, title: string): Segment[] {
  const out: Segment[] = [];
  let cp = 0;
  for (const line of text.split("\n")) {
    const lead = line.length - line.trimStart().length;
    const body = line.trim();
    if (body) out.push({ start: cp + cpLength(line.slice(0, lead)), text: body });
    cp += cpLength(line) + 1;
  }
  return out.length > 1 && bare(out[0].text) === bare(title) ? out.slice(1) : out;
}

/** 觀察直線的位置(code point,半開區間)。 */
export type ObSpan = { start: number; end: number };
type Piece = { text: string; mark: Mark | null; ob: boolean; at: number };

/** 把一段切成小塊:每塊記它屬於哪道痕跡(同一處多道取陣列裡最後一道)、在不在觀察直線裡。 */
function pieces(seg: Segment, marks: Mark[], obs: ObSpan[]): Piece[] {
  const len = cpLength(seg.text);
  const local = <T extends { start: number; end: number }>(xs: T[]) => xs
    .map(m => ({ m, a: Math.max(0, m.start - seg.start), b: Math.min(len, m.end - seg.start) }))
    .filter(x => x.a < x.b);
  const lm = local(marks), lo = local(obs);
  const cuts = [...new Set([0, len, ...lm.flatMap(x => [x.a, x.b]), ...lo.flatMap(x => [x.a, x.b])])].sort((x, y) => x - y);
  const out: Piece[] = [];
  for (let i = 0; i + 1 < cuts.length; i++) {
    const [a, b] = [cuts[i], cuts[i + 1]];
    const mark = last(lm.filter(x => x.a <= a && b <= x.b))?.m ?? null;
    const ob = lo.some(x => x.a <= a && b <= x.b);
    const prev = last(out);
    if (prev && prev.mark === mark && prev.ob === ob) prev.text += cpSlice(seg.text, a, b);
    else out.push({ text: cpSlice(seg.text, a, b), mark, ob, at: a });
  }
  return out;
}

/** 直排:短數字包縱中橫;橫排原樣。 */
function typeset(text: string, flow: PaperFlow): ReactNode {
  if (flow === "h") return text;
  return tcyRuns(text).map((r, i) => r.tcy ? <span key={i} className="paper-tcy">{r.text}</span> : <Fragment key={i}>{r.text}</Fragment>);
}

/** 量測用:在隱藏的同尺寸頁裡放這些段,看有沒有溢出(直排往左長 → 比寬)。 */
function measurer(box: HTMLElement) {
  return (page: PageSeg[]) => {
    box.replaceChildren(...page.map(s => {
      const p = document.createElement("p");
      if (s.cont) p.dataset.cont = "";
      p.textContent = s.text;
      return p;
    }));
    return box.scrollWidth <= box.clientWidth;
  };
}

/** 稿:直排一頁頁往下疊、橫排一張長紙。陪讀者提到的句子畫鉛筆波浪線(舊版不畫),選中的觀察畫直線;選字 → 浮出「帶進對話」。 */
export default function Paper({ text, title, marks, drawing, onBring, old = false, obs = [] }: {
  text: string; title: string; marks: Mark[];
  /** 正在畫的那道痕跡 id(一筆畫上去的動畫)。 */
  drawing?: string;
  onBring: (quote: string) => void;
  /** 看的是舊版:紙變淡、陪讀者的線不畫。 */
  old?: boolean;
  /** 結構圖選中的觀察在這版原文的位置。 */
  obs?: ObSpan[];
}) {
  const t = useT();
  const flow = usePaperFlow();
  const size = loadPaperSize();
  const { hover, hoverAt, jumpToTalk, registerPaper } = useLinks();
  const box = useRef<HTMLDivElement>(null);
  const measure = useRef<HTMLDivElement>(null);
  const { quote, tooLong, rect, clear } = useSelectionQuote(box);
  const [flash, setFlash] = useState<{ start: number; n: number } | null>(null);
  const segs = segments(text, title);
  const shownMarks = old ? [] : marks;

  // 直排切頁:原文、排法、字級、窗格寬改了就重排
  const [pages, setPages] = useState<PageSeg[][] | null>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = box.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.round(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  useLayoutEffect(() => {
    if (flow !== "v" || !measure.current) { setPages(null); return; }
    setPages(paginate(segments(text, title), measurer(measure.current)));
    measure.current.replaceChildren();
  }, [text, title, flow, size, width]);

  // 跳到稿:找起點不超過 span 起點的最後一段(含續段),捲過去並閃一下
  const textRef = useRef(text);
  textRef.current = text;
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const off = registerPaper(span => {
      if (span.start === null) return;
      // 位置要對得上這張稿(寬鬆比對);別版的位置不跳,免得捲到錯的段落
      if (span.end === null || bare(cpSlice(textRef.current, span.start, span.end)) !== bare(span.quote)) return;
      const ps = [...(box.current?.querySelectorAll<HTMLElement>("p[data-start]") ?? [])];
      const el = last(ps.filter(p => Number(p.dataset.start) <= span.start!));
      if (!el) return;
      const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      el.scrollIntoView?.({ block: "center", behavior: still ? "auto" : "smooth" });
      const at = Number(el.dataset.start);
      setFlash(f => ({ start: at, n: (f?.n ?? 0) + 1 }));
      clearTimeout(timer);
      timer = setTimeout(() => setFlash(null), FLASH_MS);
    });
    return () => { off(); clearTimeout(timer); };
  }, [registerPaper]);

  // 正在畫的那道:稿捲到那句(找不到元素就算了)
  useEffect(() => {
    if (!drawing) return;
    const el = box.current?.querySelector<HTMLElement>(`[data-id="${drawing}"]`);
    el?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, [drawing]);

  const hoverKey = hover ? bare(hover) : null;
  const para = (seg: PageSeg) => (
    // 段落 key 不跟著閃動變(重掛載會重播畫線、丟掉選取);要重播閃動只換裡面那層的 key
    <p key={seg.start} data-start={seg.start} data-cont={seg.cont ? "" : undefined}
      className={flash?.start === seg.start ? "is-flash" : undefined}>
      {flash?.start === seg.start && <span key={flash.n} className="paper-flash" aria-hidden="true" />}
      {pieces(seg, shownMarks, obs).map(pc => {
        const inner = pc.ob ? <span className="paper-ob">{typeset(pc.text, flow)}</span> : typeset(pc.text, flow);
        if (!pc.mark) return <Fragment key={`t${pc.at}`}>{inner}</Fragment>;
        const m = pc.mark;
        const quote = cpSlice(text, m.start, m.end);
        const cls = ["dash-mark", m.id === drawing && "is-drawing", hoverKey && bare(quote) === hoverKey && (hoverAt === null || hoverAt === m.start) && "is-hover"]
          .filter(Boolean).join(" ");
        return (
          <span key={`${m.id}@${pc.at}`} className={cls} data-id={m.id}
            style={{ "--dash-draw": `${DRAW_MS}ms` } as CSSProperties}
            role="button" tabIndex={0} onClick={() => jumpToTalk(quote)}
            onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); jumpToTalk(quote); } }}>
            {inner}
          </span>
        );
      })}
    </p>
  );
  const plain = segs.map(s => ({ ...s, cont: false }));
  return (
    <article className={["paper-sheet", flow === "h" && "dash-paper", old && "is-old"].filter(Boolean).join(" ")}
      data-size={size} data-flow={flow}>
      <div ref={box} className="paper-body">
        {flow === "h" ? plain.map(para) : (pages ?? [plain]).map((pg, i) => (
          <section key={pg[0]?.start ?? i} className="dash-paper paper-page">
            <div className="paper-cols">{pg.map(para)}</div>
            <span className="paper-folio" aria-hidden="true">{i + 1}</span>
          </section>
        ))}
      </div>
      {flow === "v" && <div ref={measure} className="paper-cols paper-measure" aria-hidden="true" />}
      {quote && (
        <div className="dash-float paper-bring" style={rect ? { position: "fixed", left: rect.left, top: rect.bottom + 8 } : undefined}>
          <button type="button" disabled={tooLong} onMouseDown={e => e.preventDefault()}
            onClick={() => { onBring(quote); clear(); }}>
            {t("reader.bring")}
          </button>
          {tooLong && <span role="status">{t("reader.tooLong")}</span>}
        </div>
      )}
    </article>
  );
}
