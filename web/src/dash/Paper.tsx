import { Fragment, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import type { DelRun, Run, TracePoint, TraceQuote } from "./api";
import { foldOf, mergeBrackets, overlay, sliceCells, type Cell, type CmpSeg } from "./compareFlow";
import { cpLength, cpSlice } from "./cp";
import { useT, type MsgKey } from "./i18n";
import { useLinks } from "./links";
import { paginate, tcyRuns, type PageSeg, type Segment } from "./paginate";
import { usePaperFlow, type PaperFlow } from "./paperFlow";
import Icon from "./Icon";
import { MAX_QUOTE, useSelectionQuote } from "./useSelectionQuote";

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

const paraKey = (seg: CmpSeg) => {
  const c = seg.cells[0];
  return c && (c.kind === "del" || c.kind === "fold") ? `${seg.start}-${c.id}` : String(seg.start);
};

const Caret = () => (
  <svg viewBox="0 0 10 8" aria-hidden="true"><path d="M1.5 7L5 1.5 8.5 7" /></svg>
);

function floatAt(r: { left: number; top: number; bottom: number }, flow: string): CSSProperties {
  if (flow === "v") {
    const right = Math.max(8, Math.min(window.innerWidth - r.left + 8, window.innerWidth - 168));
    return { position: "fixed", right, top: Math.max(8, Math.min(r.top, window.innerHeight - 56)), bottom: "auto" };
  }
  const left = Math.max(8, Math.min(r.left, window.innerWidth - 168));
  return r.bottom + 56 < window.innerHeight
    ? { position: "fixed", left, top: r.bottom + 8, bottom: "auto" }
    : { position: "fixed", left, top: Math.max(8, r.top - 8), bottom: "auto", transform: "translateY(-100%)" };
}

function inDel(box: HTMLElement | null): boolean {
  const s = document.getSelection();
  if (!box || !s || s.rangeCount === 0) return false;
  const n = s.getRangeAt(0).commonAncestorContainer;
  const d = (n.nodeType === Node.ELEMENT_NODE ? n as Element : n.parentElement)?.closest("del.cmp-del");
  return !!d && box.contains(d);
}

function hasDel(box: HTMLElement | null): boolean {
  const s = document.getSelection();
  if (!box || !s || s.rangeCount === 0) return false;
  const r = s.getRangeAt(0);
  return [...box.querySelectorAll("del, .cmp-fold")].some(d => r.intersectsNode(d));
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

export type PaperCmp = {
  runs: Run[]; clean: boolean; open: Set<string>; onToggle(id: string): void;
  focus: { id: string; n: number } | null;
  /** 上一版筆記的點(頁邊括號);只比字模式為空。 */
  points?: TracePoint[];
  /** 點了括號:選中那一點(外面退專注、窄版切去向)。 */
  onPick?: (i: number) => void;
};

type Box = { left: number; top: number; width: number; height: number };
type Brk = { start: number; end: number; ids: string[]; lit?: boolean; dim?: boolean; heavy?: boolean };
type Layer = { brk: Brk[]; hl: Box[] };
const STATE: Record<string, MsgKey> = { kept: "trace.kept", changed: "trace.changed", gone: "trace.gone", mixed: "trace.mixed" };

function rangeIn(el: Element, a: number, b: number): Range | null {
  const r = document.createRange();
  const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  let cp = 0, started = false;
  for (let n = walk.nextNode(); n; n = walk.nextNode()) {
    const chars = [...(n.textContent ?? "")];
    const off = (k: number) => chars.slice(0, k).join("").length;
    if (!started && a < cp + chars.length) { r.setStart(n, off(a - cp)); started = true; }
    if (started && b <= cp + chars.length) { r.setEnd(n, off(b - cp)); return r; }
    cp += chars.length;
  }
  return null;
}

function quoteRects(sheet: HTMLElement, q: TraceQuote, withDel: boolean): { cont: Element; r: DOMRect }[] {
  const out: { cont: Element; r: DOMRect }[] = [];
  const add = (el: Element, rs: DOMRectList | DOMRect[]) => {
    const cont = el.closest(".dash-paper");
    if (cont) for (const r of Array.from(rs)) out.push({ cont, r });
  };
  if (q.new) {
    sheet.querySelectorAll<HTMLElement>("[data-at]").forEach(el => {
      const a = Number(el.dataset.at), len = cpLength(el.textContent ?? "");
      const s = Math.max(q.new!.start, a), e = Math.min(q.new!.end, a + len);
      if (s >= e) return;
      const rg = rangeIn(el, s - a, e - a);
      if (rg && typeof rg.getClientRects === "function") add(el, rg.getClientRects());
    });
  }
  if (q.del && (withDel || q.fate === "gone")) {
    const el = sheet.querySelector(`[data-run="${q.del}"]`);
    if (el) add(el, el.getClientRects());
  }
  return out;
}

type Chunk = { kind: Cell["kind"]; id: string | null; text: string; at: number; pos: number; chars: number };

function chunks(seg: CmpSeg): Chunk[] {
  const out: Chunk[] = [];
  const chars = [...seg.text];
  seg.cells.forEach((c, k) => {
    const id = "id" in c ? c.id : null;
    const prev = out[out.length - 1];
    if (prev && prev.kind === c.kind && prev.id === id) { if (c.kind !== "fold") prev.text += chars[k]; return; }
    out.push({ kind: c.kind, id, text: c.kind === "fold" ? "" : chars[k], at: k, pos: c.at, chars: c.kind === "fold" ? c.chars : 0 });
  });
  return out;
}

function firstVisible(box: HTMLElement | null): number | null {
  const ps = [...(box?.querySelectorAll<HTMLElement>("p[data-start]") ?? [])];
  const el = ps.find(p => p.getBoundingClientRect().bottom > 0) ?? ps[0];
  return el ? Number(el.dataset.start) : null;
}

/** 稿:直排一頁頁往下疊、橫排一張長紙。陪讀者提到的句子畫鉛筆波浪線(舊版不畫),選中的觀察畫直線;選字 → 浮出「引用至對話」。 */
export default function Paper({ text, title, marks, drawing, onBring, old = false, obs = [], cmp }: {
  text: string; title: string; marks: Mark[];
  /** 正在畫的那道痕跡 id(一筆畫上去的動畫)。 */
  drawing?: string;
  onBring: (quote: string) => void;
  /** 看的是舊版:紙變淡、陪讀者的線不畫。 */
  old?: boolean;
  /** 結構圖選中的觀察在這版原文的位置。 */
  obs?: ObSpan[];
  /** 對照中:刪字/新字/摺記,鉛筆線全不畫。 */
  cmp?: PaperCmp;
}) {
  const t = useT();
  const flow = usePaperFlow();
  const size = loadPaperSize();
  const { hover, hoverAt, jumpToTalk, registerPaper, trace } = useLinks();
  const sheet = useRef<HTMLElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const measure = useRef<HTMLDivElement>(null);
  const { quote, tooLong, rect, clear } = useSelectionQuote(box);
  const [flash, setFlash] = useState<{ start: number; n: number } | null>(null);
  const runsKey = cmp ? JSON.stringify([cmp.runs.map(r => r.id), cmp.clean, [...cmp.open]]) : "";
  const folded = (r: DelRun) => !!cmp && foldOf(r, cmp.clean, cmp.open);
  const segs: CmpSeg[] = cmp ? overlay(text, title, cmp.runs, folded) : segments(text, title).map(x => ({ ...x, cells: [] }));
  const shownMarks = old || cmp ? [] : marks;
  const shownObs = cmp ? [] : obs;

  // 直排切頁:原文、排法、字級、窗格寬改了就重排
  const [paged, setPages] = useState<{ key: string; list: (CmpSeg & PageSeg)[][] } | null>(null);
  const pages = paged && paged.key === runsKey ? paged.list : null;
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
    const fits = measurer(measure.current);
    setPages({ key: runsKey, list: cmp ? paginate<CmpSeg & PageSeg>(segs, fits, sliceCells) : paginate<CmpSeg & PageSeg>(segs, fits,
      (x, a, b) => ({ ...x, start: x.start + a, text: cpSlice(x.text, a, b) })) });
    measure.current.replaceChildren();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, title, flow, size, width, runsKey]);

  // 進出對照時稿會重排:render 期間(DOM 還是舊的)記下第一個看得到的段,排好後捲回同一段
  const cmpOn = !!cmp;
  const wasCmp = useRef(cmpOn);
  const anchor = useRef<number | null>(null);
  if (wasCmp.current !== cmpOn) { anchor.current = firstVisible(box.current); wasCmp.current = cmpOn; }
  useLayoutEffect(() => {
    if (anchor.current === null || (flow === "v" && !pages)) return;
    const ps = [...(box.current?.querySelectorAll<HTMLElement>("p[data-start]") ?? [])];
    const el = last(ps.filter(p => Number(p.dataset.start) <= anchor.current!)) ?? ps[0];
    anchor.current = null;
    el?.scrollIntoView?.({ block: "start" });
  }, [cmpOn, pages, flow]);

  const focusKey = cmp?.focus ? `${cmp.focus.id}:${cmp.focus.n}` : null;
  useEffect(() => {
    if (!focusKey) return;
    const el = box.current?.querySelector<HTMLElement>(`[data-run="${focusKey.split(":")[0]}"]`);
    const p = el?.closest<HTMLElement>("p[data-start]");
    if (!p) return;
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    p.scrollIntoView?.({ block: "center", behavior: still ? "auto" : "smooth" });
    const at = Number(p.dataset.start);
    setFlash(f => ({ start: at, n: (f?.n ?? 0) + 1 }));
    const timer = setTimeout(() => setFlash(null), FLASH_MS);
    return () => clearTimeout(timer);
  }, [focusKey]);

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

  const [layers, setLayers] = useState<Layer[]>([]);
  const points = cmp?.points;
  const lit = trace.hover ?? trace.picked;
  useLayoutEffect(() => {
    const el = sheet.current;
    if (!el || !points?.length) { setLayers([]); return; }
    const conts = flow === "h" ? [el] : [...el.querySelectorAll(".paper-page")];
    const span = (rs: { cont: Element; r: DOMRect }[], c: Element) => {
      const cr = c.getBoundingClientRect();
      const mine = rs.filter(x => x.cont === c).map(x => flow === "h" ? [x.r.top - cr.top, x.r.bottom - cr.top] : [x.r.left - cr.left, x.r.right - cr.left]);
      return mine.length ? { start: Math.min(...mine.map(m => m[0])), end: Math.max(...mine.map(m => m[1])) } : null;
    };
    const moved = new Set(points.filter(p => p.kind === "moved").map(p => String(p.i)));
    const active = points.find(p => p.i === lit);
    setLayers(conts.map(c => {
      const base: Brk[] = [];
      for (const p of points) {
        if (p.fate !== "changed") continue;
        for (const q of p.quotes) {
          if (q.fate === "kept" || q.fate === "lost") continue;
          const sp = span(quoteRects(el, q, true), c);
          if (sp) base.push({ ...sp, ids: [String(p.i)] });
        }
      }
      const merged = mergeBrackets(base).map(b => {
        const ids = [...new Set(b.ids)].sort((x, y) => Number(!moved.has(x)) - Number(!moved.has(y)));
        return { ...b, ids, heavy: ids.some(i => moved.has(i)), dim: !!active };
      });
      if (!active) return { brk: merged, hl: [] };
      const mineId = String(active.i);
      const litB: Brk[] = [];
      const hl: Box[] = [];
      const cr = c.getBoundingClientRect();
      for (const q of active.quotes) {
        if (q.fate === "lost") continue;
        const rs = quoteRects(el, q, false);
        const sp = span(rs, c);
        if (sp) litB.push({ ...sp, ids: [mineId], lit: true, heavy: moved.has(mineId) });
        rs.filter(x => x.cont === c).forEach(x => hl.push({ left: x.r.left - cr.left, top: x.r.top - cr.top, width: x.r.width, height: x.r.height }));
      }
      return { brk: [...merged.filter(b => !b.ids.includes(mineId)), ...litB], hl };
    }));
  }, [points, runsKey, pages, flow, width, size, lit]); // eslint-disable-line react-hooks/exhaustive-deps

  const markLabel = (ids: string[]) => ids.map(id => {
    const p = points!.find(x => String(x.i) === id)!;
    return t("trace.mark", { kind: t(`notes.kind.${p.kind}` as MsgKey), title: p.title, state: p.label ? t(STATE[p.label]) : "" });
  }).join("；");
  const layer = (k: number) => {
    const L = layers[k];
    if (!L) return null;
    const axis = flow === "h" ? "y" : "x";
    return (
      <div className="cmp-layer">
        {L.hl.map((b, j) => <i key={`h${j}`} className="cmp-lit" style={{ left: b.left, top: b.top, width: b.width, height: b.height }} />)}
        {L.brk.map((b, j) => {
          const label = markLabel(b.ids);
          const pos = axis === "y" ? { top: `${b.start}px`, height: `${b.end - b.start}px` } : { left: `${b.start}px`, width: `${b.end - b.start}px` };
          const cls = ["cmp-bracket", b.heavy && "is-heavy", b.lit && "is-lit", b.dim && !b.lit && "is-dim"].filter(Boolean).join(" ");
          return (
            <button key={`b${j}`} type="button" data-axis={axis} aria-label={label} title={label} style={pos} className={cls}
              onClick={e => { e.stopPropagation(); const i = Number(b.ids[0]); trace.setPicked(i); cmp?.onPick?.(i); }}><i /></button>
          );
        })}
      </div>
    );
  };

  const hoverKey = hover ? bare(hover) : null;
  const foldable = (id: string) => {
    const r = cmp?.runs.find(x => x.id === id);
    return !!r && r.op === "del" && foldOf(r, cmp!.clean, new Set());
  };
  const cmpBody = (seg: CmpSeg) => chunks(seg).map(c => {
    if (c.kind === "text") return <span key={`t${c.at}`} data-at={c.pos}>{typeset(c.text, flow)}</span>;
    if (c.kind === "ins") return <ins key={`i${c.at}`} className="cmp-ins" data-run={c.id!} data-at={c.pos}>{typeset(c.text, flow)}</ins>;
    if (c.kind === "del") return (
      <Fragment key={`d${c.at}`}>
        {cmp!.open.has(c.id!) && foldable(c.id!) && (
          <button type="button" className="cmp-fold" aria-expanded="true" aria-label={t("compare.unfold")} title={t("compare.unfold")}
            onClick={() => cmp!.onToggle(c.id!)}><Caret /></button>
        )}
        <del className="cmp-del" data-run={c.id!}>{typeset(c.text, flow)}</del>
      </Fragment>
    );
    const label = t("compare.fold", { n: c.chars });
    return (
      <button key={`f${c.at}`} type="button" className="cmp-fold" data-run={c.id!} aria-expanded="false"
        aria-label={label} title={label} onClick={() => cmp!.onToggle(c.id!)}>
        <Caret />{!cmp!.clean && <span>{flow === "v" ? typeset(label.replace(/\s+/g, ""), flow) : label}</span>}
      </button>
    );
  });
  const para = (seg: CmpSeg & PageSeg) => (
    // 段落 key 不跟著閃動變(重掛載會重播畫線、丟掉選取);要重播閃動只換裡面那層的 key
    <p key={paraKey(seg)} data-start={seg.start} data-cont={seg.cont ? "" : undefined}
      className={flash?.start === seg.start ? "is-flash" : undefined}>
      {flash?.start === seg.start && <span key={flash.n} className="paper-flash" aria-hidden="true" />}
      {cmp ? cmpBody(seg) : pieces(seg, shownMarks, shownObs).map(pc => {
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
  const deleted = !!quote && !!cmp && !old && inDel(box.current);
  const bring = quote && (deleted || !(cmp && hasDel(box.current)));
  const long = tooLong && !deleted;
  return (
    <article ref={sheet} className={["paper-sheet", flow === "h" && "dash-paper", old && "is-old"].filter(Boolean).join(" ")}
      onClick={cmp ? e => { if (!(e.target as Element).closest?.(".cmp-bracket, .cmp-fold")) trace.setPicked(null); } : undefined}
      data-size={size} data-flow={flow}>
      <div ref={box} className="paper-body">
        {flow === "h" && layer(0)}
        {flow === "h" ? plain.map(para) : (pages ?? [plain]).map((pg, i) => (
          <section key={pg[0]?.start ?? i} className="dash-paper paper-page">
            <div className="paper-cols">{pg.map(para)}</div>
            <span className="paper-folio" aria-hidden="true">{i + 1}</span>
            {layer(i)}
          </section>
        ))}
      </div>
      {flow === "v" && <div ref={measure} className="paper-cols paper-measure" aria-hidden="true" />}
      {bring && (
        <div className="dash-float paper-bring" style={rect ? floatAt(rect, flow) : undefined}>
          <button type="button" disabled={long} onMouseDown={e => e.preventDefault()}
            onClick={() => { onBring(deleted ? [...quote].slice(0, MAX_QUOTE).join("") : quote); clear(); }}>
            <Icon name="talk" />{t("reader.bring")}
          </button>
          {long && <span role="status">{t("reader.tooLong")}</span>}
        </div>
      )}
    </article>
  );
}
