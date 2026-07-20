import { describe, it, expect } from "vitest";
import { WORLD, RING_XSCALE, worldPos, sparsePhase, camTransform, contentExtents, fitContent, BONE, CAP_H, MAX_ZOOM } from "../src/lib/camera";

const cx = WORLD.w / 2, cy = WORLD.h / 2;
const R1 = 645; // 環1半徑(camera.ts RING.R0 + 1*dR)

describe("地平線落子(spec D2)", () => {
  it("環1只有1顆(第7篇):落在水平端,|y-cy| ≤ 0.05R", () => {
    const p = worldPos(6, WORLD, 7); // 環0容量6 → i=6 是環1第一顆
    expect(Math.abs(p.y - cy)).toBeLessThanOrEqual(0.05 * R1);
  });
  it("環1有2顆:對稱落左右水平端", () => {
    const a = worldPos(6, WORLD, 8), b = worldPos(7, WORLD, 8);
    expect(Math.abs(a.y - cy)).toBeLessThanOrEqual(0.05 * R1);
    expect(Math.abs(b.y - cy)).toBeLessThanOrEqual(0.05 * R1);
    expect(a.x + b.x).toBeCloseTo(WORLD.w, 0); // 左右鏡像
  });
  it("occ≥3:sparsePhase 是旋轉最優(任何其他相位的 max|sin| 不會更小)", () => {
    const maxSin = (occ: number, p: number) =>
      Math.max(...Array.from({ length: occ }, (_, k) =>
        Math.abs(Math.sin(p + (k / occ) * 2 * Math.PI))));
    for (let occ = 1; occ <= 15; occ++) {
      const best = maxSin(occ, sparsePhase(occ));
      for (let s = 0; s < 360; s++) {
        expect(best).toBeLessThanOrEqual(maxSin(occ, (s / 180) * Math.PI) + 1e-9);
      }
    }
  });
  it("滿環行為不變:環0滿6顆時首顆在 π/4(既有錯開)", () => {
    const p = worldPos(0, WORLD, 6);
    expect(p.x).toBeCloseTo(cx + Math.cos(Math.PI / 4) * 360 * RING_XSCALE, 6);
    expect(p.y).toBeCloseTo(cy + Math.sin(Math.PI / 4) * 360, 6);
  });
});

describe("extents-fit(spec D1)", () => {
  it("7 篇:未夾前 fit 由寬決定(≈0.86),夾到 MAX_ZOOM", () => {
    const { halfW, halfH } = contentExtents(7);
    expect(1920 / (2 * halfW)).toBeGreaterThan(0.8);   // 地平線落子後寬邊 ≈0.86
    expect(1080 / (2 * halfH)).toBeGreaterThan(1);      // 高度綽綽有餘(孤星不再吃 y)
    expect(fitContent(7, 1920, 1080)).toBe(MAX_ZOOM);
  });
  it("30 篇:zoom 明顯高於固定世界現況,且未被夾", () => {
    const z = fitContent(30, 1920, 1080);
    expect(z).toBeGreaterThan(0.4);
    expect(z).toBeLessThan(MAX_ZOOM);
  });
  it("1 篇:被 MAX_ZOOM 夾住(少篇別太巨)", () => {
    expect(fitContent(1, 1920, 1080)).toBe(MAX_ZOOM);
  });
  it("不變量:任何篇數×常見視窗,家構圖下整具 .story(骨+兩行標題)在框內(lab 出框計數器=0)", () => {
    for (const [vw, vh] of [[1920, 1080], [1366, 768], [2560, 1440], [1280, 1024]]) {
      for (let n = 1; n <= 40; n++) {
        const z = fitContent(n, vw, vh);
        const t = camTransform(WORLD, vw, vh, z);
        for (let i = 0; i < n; i++) {
          const p = worldPos(i, WORLD, n);
          const sx = t.x + p.x * z, sy = t.y + p.y * z;
          // 縱向含 cap 兩行(截斷本病:字比骨低,底部星的標題被視窗底切掉)
          const hw = (BONE.w / 2) * z, hh = ((BONE.h + CAP_H) / 2) * z;
          expect(sx - hw).toBeGreaterThanOrEqual(-0.5);
          expect(sx + hw).toBeLessThanOrEqual(vw + 0.5);
          expect(sy - hh).toBeGreaterThanOrEqual(-0.5);
          expect(sy + hh).toBeLessThanOrEqual(vh + 0.5);
        }
      }
    }
  });
});
