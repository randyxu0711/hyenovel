import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { globSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

// 每個 animation 引用的 keyframe 名字都必須有對應的 @keyframes 定義。
// 這條不變式擋的是「刪一段以為死掉的 CSS,卻連帶刪掉別處還在用的 @keyframes」——
// 例如 .skel.reassemble .spine 用的 draw 曾被誤當 hero 區塊的一部分刪掉,退場軸就靜默不亮。
// jsdom 不跑動畫,render 測試抓不到;這裡直接對 CSS 原始碼做靜態檢查。

const KEYWORDS = new Set([
  "ease", "ease-in", "ease-out", "ease-in-out", "linear", "step-start", "step-end",
  "none", "forwards", "backwards", "both", "normal", "reverse", "alternate",
  "alternate-reverse", "infinite", "running", "paused", "initial", "inherit", "unset",
]);
const isTime = (t: string) => /^-?[\d.]+m?s$/.test(t);
const isNum = (t: string) => /^-?[\d.]+$/.test(t);

function cssFiles(): string[] {
  const srcDir = resolve(dirname(fileURLToPath(import.meta.url)), "../src");
  return globSync("**/*.css", { cwd: srcDir }).map(f => resolve(srcDir, f));
}

describe("CSS keyframes 完整性", () => {
  it("每個 animation 引用的 keyframe 名都有 @keyframes 定義", () => {
    const defined = new Set<string>();
    const refs: { name: string; file: string }[] = [];

    for (const path of cssFiles()) {
      const css = readFileSync(path, "utf8");
      const file = path.split("/src/")[1] ?? path;
      for (const m of css.matchAll(/@keyframes\s+([\w-]+)/g)) defined.add(m[1]);
      // animation / animation-name 簡寫:name 是「非時間、非數字、非關鍵字」的那個 token
      for (const m of css.matchAll(/animation(?:-name)?\s*:\s*([^;}]+)/g)) {
        const value = m[1].replace(/[\w-]+\([^)]*\)/g, " ");   // 拔掉 cubic-bezier()/steps() 等函式
        for (const part of value.split(",")) {                  // 一條可掛多個動畫
          const name = part.trim().split(/\s+/)
            .find(t => t && !KEYWORDS.has(t) && !isTime(t) && !isNum(t));
          if (name) refs.push({ name, file });
        }
      }
    }

    const dangling = refs.filter(r => !defined.has(r.name));
    expect(dangling, `無定義的 @keyframes 引用:${JSON.stringify(dangling)}`).toEqual([]);
  });
});
