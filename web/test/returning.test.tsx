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

describe("逆俯衝出場", () => {
  it("單篇按退 → overlay 先收合(.out)→ 稍後才回目錄", async () => {
    vi.useFakeTimers();
    const slug = (index as { stories: { slug: string }[] }).stories[0].slug;
    const { container } = at(`/story/${slug}`);
    await act(async () => {});                                   // 讓 getStory 落定
    fireEvent.click(container.querySelector(".chrome-back")!);
    expect(container.querySelector(".single-overlay.out")).toBeTruthy();   // 收合中
    expect(container.querySelector(".single-overlay")).toBeTruthy();        // 還沒卸載
    await act(async () => { vi.advanceTimersByTime(500); });   // 過 OVERLAY_OUT_MS,nav 回目錄並 flush
    expect(container.querySelector(".single-overlay")).toBeNull();  // 已回目錄、overlay 卸載
  });
});
