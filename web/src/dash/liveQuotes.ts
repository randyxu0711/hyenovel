import { cpLength } from "./cp";

/** 與 den/spans.py 的 MIN_QUOTE/MAX_QUOTE 一致。 */
const MIN_QUOTE = 2, MAX_QUOTE = 400;
/** 全是標點/空白(如「……」):den 也不認。 */
const blank = (s: string) => /^[\p{P}\s]*$/u.test(s);

/** 串流中的「」引文:規則同 den 的 quotes_in(成對、2–400 字、巢狀略過、全標點略過、去重保序),
 *  只是分段餵進來 —— 每次 push 回傳這次新收尾的引文。 */
export function liveQuotes(): { push(chunk: string): string[] } {
  let text = "", i = 0;
  const seen = new Set<string>();
  return {
    push(chunk) {
      text += chunk;
      const out: string[] = [];
      for (;;) {
        const a = text.indexOf("「", i);
        if (a === -1) { i = text.length; break; }
        const b = text.indexOf("」", a + 1);
        if (b === -1) { i = a; break; }   // 還沒收尾:下次從這個「再看
        const inner = text.slice(a + 1, b);
        i = b + 1;
        if (inner.includes("「")) continue;   // 巢狀:整段略過
        const n = cpLength(inner);
        if (n < MIN_QUOTE || n > MAX_QUOTE || blank(inner) || seen.has(inner)) continue;
        seen.add(inner);
        out.push(inner);
      }
      return out;
    },
  };
}
