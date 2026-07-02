import { useEffect, useRef } from "react";
import type { VizData } from "../types";

interface Mark { start: number; end: number; id: string; type: string; label: string }
const C: Record<string, string> = {
  technique: "var(--c-technique)", effect: "var(--c-effect)", theme: "var(--c-theme)",
  motif: "var(--c-motif)", beat: "var(--c-beat)", character: "var(--c-character)",
};

/**
 * 原文 + 可討論點:分析引用過的句子點得下去(→ 討論),句尾綴一顆該類型顏色的小星標。
 * 字元區段重疊時,依 (start 早、跨度長) 排序後每字元歸屬「第一個」蓋到它的節點。
 */
export default function SourceAnnotated(
  { source, viz, highlight, onDiscuss }:
  { source: string; viz: VizData; highlight: { start: number; end: number } | null; onDiscuss: (id: string) => void },
) {
  const ref = useRef<HTMLElement | null>(null);
  const boxRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const scroller = boxRef.current?.closest(".sb-textview") as HTMLElement | null;
    // 直排 vertical-rl 是右起:捲軸預設停在左(最後一行),要撥到最右才是第一行
    if (highlight && ref.current) ref.current.scrollIntoView({ block: "center", inline: "center" });
    else if (scroller) scroller.scrollLeft = scroller.scrollWidth;
  }, [highlight]);
  // 直排頁把直向滾輪接成水平:往下滾=往下文讀(內容左移),往上滾回上文
  useEffect(() => {
    const scroller = boxRef.current?.closest(".sb-textview") as HTMLElement | null;
    if (!scroller) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.deltaY) return; // 觸控板水平滑動照舊由瀏覽器處理
      e.preventDefault();
      scroller.scrollLeft -= e.deltaY;
    };
    scroller.addEventListener("wheel", onWheel, { passive: false });
    return () => scroller.removeEventListener("wheel", onWheel);
  }, []);

  const marks: Mark[] = [];
  for (const n of viz.nodes)
    for (const e of n.evidence)
      if (e.start != null && e.end != null && e.end > e.start && e.start < source.length)
        marks.push({ start: e.start, end: Math.min(e.end, source.length), id: n.id, type: n.type, label: n.label });
  marks.sort((a, b) => a.start - b.start || (b.end - b.start) - (a.end - a.start));

  const owner = new Array<number>(source.length).fill(-1);
  marks.forEach((m, mi) => { for (let i = m.start; i < m.end; i++) if (owner[i] === -1) owner[i] = mi; });

  const segs: { o: number; text: string; end: number }[] = [];
  let i = 0;
  while (i < source.length) {
    const o = owner[i]; let j = i + 1;
    while (j < source.length && owner[j] === o) j++;
    segs.push({ o, text: source.slice(i, j), end: j }); i = j;
  }

  let hlDone = false;
  return (
    <>
      <div className="src-hint">欄側有細線的段落是分析過的可討論點,點它就那段跟編輯討論。</div>
      <div className="src-annot" ref={boxRef}>
        {segs.map((s, k) => {
          if (s.o === -1) return <span key={k}>{s.text}</span>;
          const m = marks[s.o];
          const isHl = !!highlight && m.start >= highlight.start && m.end <= highlight.end;
          const attach = isHl && !hlDone;
          if (attach) hlDone = true;
          return (
            <mark key={k} className={`ann${isHl ? " hl" : ""}`} title={`就「${m.label}」討論`}
              style={{ "--dot": C[m.type] } as React.CSSProperties}
              ref={attach ? (ref as React.RefObject<HTMLElement>) : undefined}
              onClick={() => onDiscuss(m.id)}>
              {s.text}
            </mark>
          );
        })}
      </div>
    </>
  );
}
