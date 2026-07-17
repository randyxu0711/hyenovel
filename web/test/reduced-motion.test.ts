import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

// theme.css 的全域減動兜底是所有 CSS 動畫的出路(全站 30+ 個動畫只有 6 個自帶精細規則)。
// 它被刪掉時畫面完全正常,只有開 prefers-reduced-motion 的人受害——jsdom 不跑動畫也不模擬
// media query,render 測試永遠抓不到。故直接對 CSS 原始碼驗這道承重牆還在。
// 前科:刪 hero 區塊時連帶刪掉別處還在用的 @keyframes draw,退場軸靜默不亮。

const themeCss = () =>
  readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "../src/theme.css"), "utf8");

function reduceBlock(css: string): string | null {
  const m = /@media[^{]*prefers-reduced-motion:\s*reduce[^{]*\{/.exec(css);
  if (!m) return null;
  let i = m.index + m[0].length, depth = 1;
  while (i < css.length && depth > 0) {
    if (css[i] === "{") depth++;
    else if (css[i] === "}") depth--;
    i++;
  }
  return css.slice(m.index, i);
}

describe("全域減動兜底", () => {
  it("theme.css 有 prefers-reduced-motion:reduce 區塊", () => {
    expect(reduceBlock(themeCss()), "theme.css 的全域減動 reset 不見了").not.toBeNull();
  });

  it("以通用選擇器守住 animation/transition,且帶 !important 壓得過個別規則", () => {
    const block = reduceBlock(themeCss());
    expect(block).not.toBeNull();
    expect(block!, "全域 reset 沒套在 *,*::before,*::after 上").toMatch(/\*\s*,\s*\*::before\s*,\s*\*::after/);
    for (const prop of ["animation-duration", "animation-iteration-count", "transition-duration"]) {
      expect(block!, `全域 reset 少了 ${prop}`).toMatch(new RegExp(`${prop}\\s*:[^;]*!important`));
    }
  });
});
