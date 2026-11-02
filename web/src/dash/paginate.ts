import { cpLength, cpSlice } from "./cp";

/** 原文的一段:start = 它在原文的 code point 起點。 */
export type Segment = { start: number; text: string };
/** 頁上的一段;cont = 從上一頁接過來的續段(不縮排)。 */
export type PageSeg = Segment & { cont: boolean };

/** 直排切頁:貪婪放段,放不下就在段內二分找最大切點;空頁連一個字都放不下時硬放一個字(保證前進)。 */
export function paginate(segs: Segment[], fits: (page: PageSeg[]) => boolean): PageSeg[][] {
  const pages: PageSeg[][] = [];
  let page: PageSeg[] = [];
  const queue: PageSeg[] = segs.map(s => ({ ...s, cont: false }));
  while (queue.length) {
    const seg = queue.shift()!;
    if (fits([...page, seg])) { page.push(seg); continue; }
    const len = cpLength(seg.text);
    let lo = 0, hi = len - 1;   // 找最大的 k(< len)使前 k 字放得下
    while (lo < hi) {
      const mid = Math.ceil((lo + hi) / 2);
      if (fits([...page, { ...seg, text: cpSlice(seg.text, 0, mid) }])) lo = mid; else hi = mid - 1;
    }
    const k = lo === 0 && page.length === 0 ? 1 : lo;
    if (k === 0) { pages.push(page); page = []; queue.unshift(seg); continue; }   // 整段搬到下一頁
    page.push({ ...seg, text: cpSlice(seg.text, 0, k) });
    pages.push(page);
    page = [];
    if (k < len) queue.unshift({ start: seg.start + k, text: cpSlice(seg.text, k), cont: true });
  }
  if (page.length) pages.push(page);
  return pages;
}

/** 直排的短數字:連續 1–2 個半形數字、前後不接英數 → tcy(縱中橫)。 */
export function tcyRuns(text: string): { text: string; tcy: boolean }[] {
  const out: { text: string; tcy: boolean }[] = [];
  const re = /(?<![A-Za-z0-9])[0-9]{1,2}(?![A-Za-z0-9])/g;
  let at = 0;
  for (const m of text.matchAll(re)) {
    if (m.index! > at) out.push({ text: text.slice(at, m.index), tcy: false });
    out.push({ text: m[0], tcy: true });
    at = m.index! + m[0].length;
  }
  if (at < text.length || !out.length) out.push({ text: text.slice(at), tcy: false });
  return out;
}
