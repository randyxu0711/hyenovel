/** den 回的位移是 Python code point 索引;JS 字串是 UTF-16。補充平面字(如 𠀋)在 JS 佔 2 個 unit、在 den 算 1。 */

export const cpLength = (s: string): number => {
  let n = 0;
  for (const _ of s) n++;
  return n;
};

/** 以 code point 切片;語意同 Python s[start:end](不接受負數:夾到 0)。 */
export const cpSlice = (s: string, start: number, end?: number): string =>
  Array.from(s).slice(Math.max(0, start), end === undefined ? undefined : Math.max(0, end)).join("");

/** code point 位移 → UTF-16 位移(給 DOM Range 用)。越界夾到 [0, s.length]。 */
export const cpToUnit = (s: string, cp: number): number => {
  if (cp <= 0) return 0;
  let n = 0, unit = 0;
  for (const ch of s) {
    if (n >= cp) break;
    unit += ch.length;
    n++;
  }
  return unit;
};
