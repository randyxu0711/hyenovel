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
  useEffect(() => { if (highlight && ref.current) ref.current.scrollIntoView({ block: "center" }); }, [highlight]);

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
      <div className="src-hint">句尾的小星標是分析過的可討論點,點該句就那一點跟編輯討論。</div>
      <div className="src-annot">
        {segs.map((s, k) => {
          if (s.o === -1) return <span key={k}>{s.text}</span>;
          const m = marks[s.o];
          const isHl = !!highlight && m.start >= highlight.start && m.end <= highlight.end;
          const attach = isHl && !hlDone;
          if (attach) hlDone = true;
          const tail = s.end === m.end; // 一顆星只落在該節點段落的末字
          return (
            <mark key={k} className={`ann${isHl ? " hl" : ""}`} title={`就「${m.label}」討論`}
              ref={attach ? (ref as React.RefObject<HTMLElement>) : undefined}
              onClick={() => onDiscuss(m.id)}>
              {s.text}{tail && <sup className="ann-dot" style={{ color: C[m.type] }}>✦</sup>}
            </mark>
          );
        })}
      </div>
    </>
  );
}
