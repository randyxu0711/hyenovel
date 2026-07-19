import { describe, it, expect } from "vitest";
import { WORLD, RING_XSCALE, worldPos, sparsePhase } from "../src/lib/camera";

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
