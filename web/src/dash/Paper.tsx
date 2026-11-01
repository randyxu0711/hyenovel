import { useEffect, useRef, useState, type CSSProperties } from "react";
import { cpLength, cpSlice } from "./cp";
import { useT } from "./i18n";
import { useLinks } from "./links";
import { useThemeState } from "./theme";
import { useCharacters } from "./useCharacters";
import { useSelectionQuote } from "./useSelectionQuote";

/** 讀者在稿上的一道痕跡:位移是原文的 code point 索引(den 給的)。 */
export type Mark = { start: number; end: number; character: string; id: string };
type Segment = { start: number; text: string };

const MARKS = ["pencil", "highlighter", "circle"];
const FLASH_MS = 1400;
const last = <T,>(xs: T[]): T | undefined => xs[xs.length - 1];
const bare = (s: string) => s.normalize("NFKC").replace(/[\p{P}\p{S}\s]/gu, "");

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

/** 把一段切成「沒痕跡 / 某道痕跡」的小塊;同一處有多道時取陣列裡最後一道。 */
function pieces(seg: Segment, marks: Mark[]): { text: string; mark: Mark | null }[] {
  const len = cpLength(seg.text);
  const local = marks
    .map(m => ({ m, a: Math.max(0, m.start - seg.start), b: Math.min(len, m.end - seg.start) }))
    .filter(x => x.a < x.b);
  const cuts = [...new Set([0, len, ...local.flatMap(x => [x.a, x.b])])].sort((x, y) => x - y);
  const out: { text: string; mark: Mark | null }[] = [];
  for (let i = 0; i + 1 < cuts.length; i++) {
    const [a, b] = [cuts[i], cuts[i + 1]];
    const mark = last(local.filter(x => x.a <= a && b <= x.b))?.m ?? null;
    const prev = last(out);
    if (prev && prev.mark === mark) prev.text += cpSlice(seg.text, a, b);
    else out.push({ text: cpSlice(seg.text, a, b), mark });
  }
  return out;
}

/** 稿:一張紙,讀者痕跡畫在上面;選字 → 浮出「帶進對話」。 */
export default function Paper({ text, title, marks, drawing, onBring }: {
  text: string; title: string; marks: Mark[];
  /** 正在畫的那道痕跡 id(一筆畫上去的動畫)。 */
  drawing?: string;
  onBring: (quote: string) => void;
}) {
  const t = useT();
  const chars = useCharacters();
  const { mode } = useThemeState();
  const { hover, jumpToTalk, registerPaper } = useLinks();
  const box = useRef<HTMLDivElement>(null);
  const { quote, tooLong, rect, clear } = useSelectionQuote(box);
  const [flash, setFlash] = useState<{ start: number; n: number } | null>(null);
  const segs = segments(text, title);

  // 跳到稿:找包含 span 起點的那段,捲過去並閃一下
  const segsRef = useRef(segs);
  segsRef.current = segs;
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const off = registerPaper(span => {
      if (span.start === null) return;
      const seg = last(segsRef.current.filter(s => s.start <= span.start!));
      if (!seg) return;
      const el = box.current?.querySelector<HTMLElement>(`p[data-start="${seg.start}"]`);
      const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      el?.scrollIntoView?.({ block: "center", behavior: still ? "auto" : "smooth" });
      setFlash(f => ({ start: seg.start, n: (f?.n ?? 0) + 1 }));
      clearTimeout(timer);
      timer = setTimeout(() => setFlash(null), FLASH_MS);
    });
    return () => { off(); clearTimeout(timer); };
  }, [registerPaper]);

  const hoverKey = hover ? bare(hover) : null;
  return (
    <article className="dash-paper paper-sheet">
      <div ref={box}>
        {segs.map(seg => (
          <p key={flash?.start === seg.start ? `${seg.start}-${flash.n}` : seg.start} data-start={seg.start}
            className={flash?.start === seg.start ? "is-flash" : undefined}>
            {pieces(seg, marks).map((pc, i) => {
              if (!pc.mark) return pc.text;
              const m = pc.mark;
              const c = chars.byId(m.character);
              const quote = cpSlice(text, m.start, m.end);
              const cls = ["dash-mark", m.id === drawing && "is-drawing", hoverKey && bare(quote) === hoverKey && "is-hover"]
                .filter(Boolean).join(" ");
              return (
                <span key={i} className={cls} data-mark={MARKS.includes(c.mark) ? c.mark : "pencil"} data-id={m.id}
                  style={{ "--dash-mark": c.colors[mode].fill } as CSSProperties}
                  role="button" tabIndex={0} onClick={() => jumpToTalk(quote)}
                  onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); jumpToTalk(quote); } }}>
                  {pc.text}
                </span>
              );
            })}
          </p>
        ))}
      </div>
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
