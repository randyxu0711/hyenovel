import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

// 字的家法(spec 2026-07-20 art-immersion §3A)守門:
// 字階 token 單一正本在 theme.css;Inter 除名(它只服務拉丁/數字,AI 樣板第一名)。
// 沿用 css-keyframes.test.ts 的教訓:readdirSync({recursive}) 而非 globSync(Node 22+,CI 跑 20);
// 掃描類測試必須先驗「真的掃到檔」——不 crash 和掃了 0 個檔都是綠的。

const srcDir = resolve(dirname(fileURLToPath(import.meta.url)), "../src");
const srcFiles = (ext: string) =>
  readdirSync(srcDir, { recursive: true }).map(String)
    .filter(f => f.endsWith(ext)).map(f => resolve(srcDir, f));

describe("字的家法", () => {
  it("theme.css 定義完整七階 + 展示級總額", () => {
    const theme = readFileSync(resolve(srcDir, "theme.css"), "utf8");
    for (const decl of [
      "--t-micro:11px", "--t-caption:13px", "--t-body:15px", "--t-lead:17px",
      "--t-title:21px", "--t-display:27px", "--t-hero:34px", "--t-total:46px",
    ]) expect(theme, `theme.css 缺 ${decl}`).toContain(decl);
  });

  it('"Inter" 已除名(css/ts/tsx 全掃)', () => {
    const files = [...srcFiles(".css"), ...srcFiles(".ts"), ...srcFiles(".tsx")];
    expect(files.length).toBeGreaterThan(10); // 驗真的掃到檔
    const hits = files.filter(p => readFileSync(p, "utf8").includes('"Inter"'));
    expect(hits, `還掛著 Inter:${hits.join(", ")}`).toEqual([]);
  });
});
