import { describe, it, expect } from "vitest";
import { WORLD, fitScale, stageZoom, fitContent, camTransform, worldPos, cameraPose, usageLayout, ZOOM_FLOOR, labelsResident } from "../src/lib/camera";

describe("camera math", () => {
  it("WORLD 是 2600x1500", () => {
    expect(WORLD).toEqual({ w: 2600, h: 1500 });
  });
  it("fitScale 取較小比例", () => {
    expect(fitScale({ w: 1000, h: 500 }, 2000, 2000)).toBe(2); // min(2000/1000,2000/500)=2
  });
  it("stageZoom:catalog=家構圖、overview=家×0.9、single=固定世界×1.5", () => {
    const home = fitContent(7, 1920, 1080);
    expect(stageZoom("catalog", 7, 1920, 1080)).toBe(home);
    expect(stageZoom("overview", 7, 1920, 1080)).toBeCloseTo(home * 0.9);
    expect(stageZoom("single", 7, 1920, 1080)).toBeCloseTo(fitScale(WORLD, 1920, 1080) * 1.5);
  });
  it("camTransform 把 focus 置中於視窗", () => {
    const t = camTransform({ w: 1000, h: 1000 }, 800, 600, 2, { x: 100, y: 50 });
    expect(t.scale).toBe(2);
    expect(t.x).toBe(800 / 2 - 100 * 2); // 200
    expect(t.y).toBe(600 / 2 - 50 * 2);  // 200
  });
  it("camTransform 無 focus 時置中世界中心", () => {
    const t = camTransform({ w: 1000, h: 1000 }, 800, 600, 1);
    expect(t.x).toBe(400 - 500);
    expect(t.y).toBe(300 - 500);
  });
  it("worldPos 對同一 index 穩定,且落在世界內", () => {
    const a = worldPos(3, WORLD), b = worldPos(3, WORLD);
    expect(a).toEqual(b);
    expect(a.x).toBeGreaterThan(0); expect(a.x).toBeLessThan(WORLD.w);
    expect(a.y).toBeGreaterThan(0); expect(a.y).toBeLessThan(WORLD.h);
  });
  it("cameraPose:非 single 忽略 focus;single 才對焦(與 Camera 分派一致)", () => {
    expect(cameraPose("catalog", 7, 1920, 1080, { x: 9, y: 9 }))
      .toEqual(cameraPose("catalog", 7, 1920, 1080));
    const t = cameraPose("single", 7, 1920, 1080, { x: 100, y: 50 });
    expect(t.x).toBeCloseTo(1920 / 2 - 100 * t.scale);
    expect(t.y).toBeCloseTo(1080 / 2 - 50 * t.scale);
  });
  it("usageLayout:目錄槽位以 overlay 視窗靜態 fit(count=1 落地平線右端、y 置中)", () => {
    const { z, pts } = usageLayout(1, 1024, 768);
    // count=1:worldPos(0)=(cx+540, cy) → halfW=540+150,halfH=0+92
    expect(z).toBeCloseTo(Math.min(0.75, 1024 / (2 * 690), 768 / (2 * 92)));
    expect(pts[0].y).toBeCloseTo(384);
    expect(pts[0].x).toBeCloseTo(512 + 540 * z);
  });
  it("可讀地板:14px 螢幕字 ÷ cap 字級(--t-display 27px);地板上常駐、下退 hover", () => {
    expect(ZOOM_FLOOR).toBeCloseTo(14 / 27);
    expect(labelsResident(ZOOM_FLOOR)).toBe(true);
    expect(labelsResident(0.5)).toBe(false);
  });
});
