import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, fireEvent, act } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Journey from "../src/journey/Journey";
import index from "./fixtures/index.json";
import viz from "./fixtures/viz.json";

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    clearRect: vi.fn(), beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(),
  } as unknown as CanvasRenderingContext2D);
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    const body = url.includes("index.json") ? index : url.includes("viz.json") ? viz : null;
    if (body) return Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);
    return Promise.resolve({ ok: true, text: () => Promise.resolve("　　原文一段。") } as Response);
  }));
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

function at(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="/" element={<Journey />} /><Route path="/story/:slug" element={<Journey />} /></Routes>
    </MemoryRouter>,
  );
}

describe("退場 = 鏡頭抬起", () => {
  it("單篇按退 → overlay 先淡出(.out)→ 稍後才回目錄", async () => {
    vi.useFakeTimers();
    const slug = (index as { stories: { slug: string }[] }).stories[0].slug;
    const { container } = at(`/story/${slug}`);
    await act(async () => {});                                   // 讓 getStory 落定
    fireEvent.click(container.querySelector(".chrome-back")!);
    expect(container.querySelector(".single-overlay.out")).toBeTruthy();   // 淡出中
    expect(container.querySelector(".single-overlay")).toBeTruthy();        // 還沒卸載
    await act(async () => { vi.advanceTimersByTime(200); });   // 未過 OVERLAY_OUT_MS(300)
    expect(container.querySelector(".single-overlay")).toBeTruthy();
    await act(async () => { vi.advanceTimersByTime(150); });   // 過了 → nav 回目錄並 flush
    expect(container.querySelector(".single-overlay")).toBeNull();  // 已回目錄、overlay 卸載
  });

  // 回到目錄的星是終態的骨,不重組 —— 離開只是視角收回,骨一直在自己的槽位上。
  // reassemble 的前提(碎片剛炸開、正在外面)在退場那一刻早就不成立(burst 是幾分鐘前的事)。
  it("回到目錄後那顆星不演重組(骨已在終態)", async () => {
    vi.useFakeTimers();
    const slug = (index as { stories: { slug: string }[] }).stories[0].slug;
    const { container } = at(`/story/${slug}`);
    await act(async () => {});
    fireEvent.click(container.querySelector(".chrome-back")!);
    await act(async () => { vi.advanceTimersByTime(500); });
    // 先確認骨真的畫出來了 —— 不然「沒有 .reassemble」可能只是 viz 還沒載到,是假綠
    expect(container.querySelector(".skel")).toBeTruthy();
    expect(container.querySelector(".skel.reassemble")).toBeNull();
    expect(container.querySelector(".story.returning")).toBeNull();
  });
});
