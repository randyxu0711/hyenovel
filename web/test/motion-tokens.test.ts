import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { EASE_HOUSE, D_CAM } from "../src/lib/motion";

// 運鏡家法(spec art-immersion §3C):簽名緩動與時長族單一口音。
// framer-motion 吃不到 CSS var → motion.ts 是 TS 鏡像,這裡釘兩邊同步(不同步=兩種口音回來了)。
const src = (f: string) =>
  readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "../src", f), "utf8");

describe("運鏡家法", () => {
  it("theme.css 定義簽名緩動與時長族", () => {
    const theme = src("theme.css");
    for (const d of ["--ease-house:cubic-bezier(.66,0,.2,1)",
      "--d-quick:.3s", "--d-soft:.6s", "--d-scene:.9s", "--d-cam:1.4s"])
      expect(theme, `theme.css 缺 ${d}`).toContain(d);
  });
  it("motion.ts 與 theme.css 同步(TS 鏡像不許漂移)", () => {
    const m = /--ease-house:cubic-bezier\(([^)]+)\)/.exec(src("theme.css"))!;
    expect(EASE_HOUSE).toEqual(m[1].split(",").map(Number));
    const d = /--d-cam:([.\d]+)s/.exec(src("theme.css"))!;
    expect(D_CAM).toBe(Number(d[1]));
  });
  it("簽名曲線不得以字面量散落 journey.css/lab.css(要用 var(--ease-house))", () => {
    for (const f of ["journey/journey.css", "lab/lab.css"]) {
      expect(src(f)).not.toContain("cubic-bezier(.66,0,.2,1)");
      expect(src(f), `${f} 沒半處引用 --ease-house?掃描沒做`).toContain("var(--ease-house)");
    }
  });
});
