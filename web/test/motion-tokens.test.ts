import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { EASE_HOUSE, D_CAM, D_CAM_OUT, camDuration } from "../src/lib/motion";

// 運鏡家法(spec art-immersion §3C):簽名緩動與時長族單一口音。
// framer-motion 吃不到 CSS var → motion.ts 是 TS 鏡像,這裡釘兩邊同步(不同步=兩種口音回來了)。
const src = (f: string) =>
  readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "../src", f), "utf8");

describe("運鏡家法", () => {
  it("theme.css 定義簽名緩動與時長族", () => {
    const theme = src("theme.css");
    for (const d of ["--ease-house:cubic-bezier(.66,0,.2,1)",
      "--d-quick:.3s", "--d-soft:.6s", "--d-scene:.9s", "--d-cam:1.4s", "--d-cam-out:.8s"])
      expect(theme, `theme.css 缺 ${d}`).toContain(d);
  });
  it("motion.ts 與 theme.css 同步(TS 鏡像不許漂移)", () => {
    const m = /--ease-house:cubic-bezier\(([^)]+)\)/.exec(src("theme.css"))!;
    expect(EASE_HOUSE).toEqual(m[1].split(",").map(Number));
    const d = /--d-cam:([.\d]+)s/.exec(src("theme.css"))!;
    expect(D_CAM).toBe(Number(d[1]));
    const o = /--d-cam-out:([.\d]+)s/.exec(src("theme.css"))!;
    expect(D_CAM_OUT).toBe(Number(o[1]));
  });
  // 進退場非對稱是我們的政策(俯衝是儀式要慢、抬起是視野張開要快),不是 framer-motion 的行為 → 該測。
  it("camDuration:只有離開單篇走 --d-cam-out,其餘一律 --d-cam", () => {
    expect(camDuration("single", "catalog")).toBe(D_CAM_OUT);
    expect(camDuration("single", "overview")).toBe(D_CAM_OUT);
    expect(camDuration("catalog", "single")).toBe(D_CAM);   // 進場俯衝不加速
    expect(camDuration("single", "single")).toBe(D_CAM);    // 單篇內換焦點不是退場
    expect(camDuration("overview", "catalog")).toBe(D_CAM);
    expect(camDuration(null, "catalog")).toBe(D_CAM);       // 首次掛載無來向
  });

  it("簽名曲線不得以字面量散落 journey.css/lab.css(要用 var(--ease-house))", () => {
    for (const f of ["journey/journey.css", "lab/lab.css"]) {
      expect(src(f)).not.toContain("cubic-bezier(.66,0,.2,1)");
      expect(src(f), `${f} 沒半處引用 --ease-house?掃描沒做`).toContain("var(--ease-house)");
    }
  });
});
