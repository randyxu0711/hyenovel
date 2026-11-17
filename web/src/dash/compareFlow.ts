import type { DelRun, Run } from "./api";
import type { Segment } from "./paginate";
import { segments } from "./Paper";

export const FOLD_MIN = 34;
const FOLD_PAD = 5;
const PAD = "\uE000";

export type Cell =
  | { kind: "text"; at: number }
  | { kind: "ins"; id: string; at: number }
  | { kind: "del"; id: string; at: number }
  | { kind: "fold"; id: string; at: number; chars: number };
export type CmpSeg = Segment & { cells: Cell[] };

export const foldOf = (r: DelRun, clean: boolean, open: Set<string>) =>
  !open.has(r.id) && (clean || (!r.pinned && r.chars >= FOLD_MIN));

const isBlank = (c: string) => /\s/.test(c);

/** 新原文 + 插回去的刪字(或摺記佔位)排成顯示文字,依換行切段;cells[k] 記第 k 個 code point 是誰。 */
export function overlay(text: string, title: string, runs: Run[], folded: (r: DelRun) => boolean): CmpSeg[] {
  const chars = [...text];
  const ins = runs.filter((r): r is Extract<Run, { op: "ins" }> => r.op === "ins");
  const dels = runs.filter((r): r is DelRun => r.op === "del");
  const out: string[] = [];
  const cells: Cell[] = [];
  const put = (at: number) => {
    for (const r of dels) {
      if (r.at !== at) continue;
      if (folded(r)) {
        for (let k = 0; k < FOLD_PAD; k++) { out.push(PAD); cells.push({ kind: "fold", id: r.id, at, chars: r.chars }); }
      } else {
        for (const c of r.text) { out.push(c); cells.push({ kind: "del", id: r.id, at }); }
      }
    }
  };
  chars.forEach((c, i) => {
    put(i);
    out.push(c);
    const hit = ins.find(r => r.start <= i && i < r.end);
    cells.push(hit ? { kind: "ins", id: hit.id, at: i } : { kind: "text", at: i });
  });
  put(chars.length);

  const plain = segments(text, title);
  const skipped = plain.length < segments(text, "").length;
  const floor = skipped ? plain[0].start : -1;
  const segs: CmpSeg[] = [];
  let a = 0;
  for (let i = 0; i <= out.length; i++) {
    if (i < out.length && out[i] !== "\n") continue;
    let s = a, e = i;
    while (s < e && isBlank(out[s])) s++;
    while (e > s && isBlank(out[e - 1])) e--;
    if (s < e) {
      const seg = { start: cells[s].at, text: out.slice(s, e).join(""), cells: cells.slice(s, e) };
      if (seg.start >= floor) segs.push(seg);
    }
    a = i + 1;
  }
  return segs;
}

export function sliceCells<T extends CmpSeg>(seg: T, a: number, b: number): T {
  const cells = seg.cells.slice(a, b);
  return { ...seg, text: [...seg.text].slice(a, b).join(""), cells, start: cells[0]?.at ?? seg.start };
}

export type Bracket = { start: number; end: number; ids: string[] };

export function mergeBrackets(bs: Bracket[], gap = 6): Bracket[] {
  const out: Bracket[] = [];
  for (const b of [...bs].sort((x, y) => x.start - y.start)) {
    const last = out[out.length - 1];
    if (last && b.start - last.end <= gap) {
      last.end = Math.max(last.end, b.end);
      last.ids.push(...b.ids);
    } else out.push({ ...b, ids: [...b.ids] });
  }
  return out;
}
