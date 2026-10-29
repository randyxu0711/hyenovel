import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Journey from "../src/journey/Journey";
import { denIndex } from "./den-index";
import viz from "./fixtures/viz.json";

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    clearRect: vi.fn(), beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(),
  } as unknown as CanvasRenderingContext2D);
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
    matches: true, addListener: vi.fn(), removeListener: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
  }));
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    const body = url === "/api/stories" ? denIndex : url.endsWith("/viz") ? viz : null;
    if (body) return Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);
    return Promise.resolve({ ok: true, text: () => Promise.resolve("　　原文一段。") } as Response);
  }));
});

describe("用量入口(4a 期間隱藏;UsageMap 元件留待重設計)", () => {
  it("目錄層不渲染用量入口,也不打 /api/usage", async () => {
    const r = render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes><Route path="/" element={<Journey />} /></Routes>
      </MemoryRouter>);
    await waitFor(() => expect(r.getByRole("button", { name: /進入/ })).toBeTruthy());
    fireEvent.click(r.getByRole("button", { name: /進入/ }));
    await waitFor(() => expect(r.container.querySelector(".field")).toBeTruthy());
    expect(r.container.querySelector(".usage-entry")).toBeNull();
    const urls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map(c => String(c[0]));
    expect(urls.some(u => u.includes("/api/usage"))).toBe(false);
  });

  // 用量上限 toast 在場時,右下角讓位(journey 掛 toasting);toast 與入口是否同住不再相關,類別仍在。
  it("用量上限 toast 在場時,journey 掛 toasting", async () => {
    localStorage.setItem("hy:usageLimit", String(Math.floor(Date.now() / 1000) + 3600));
    const r = render(<MemoryRouter initialEntries={["/"]}><Routes><Route path="/" element={<Journey />} /></Routes></MemoryRouter>);
    await waitFor(() => expect(r.getByRole("button", { name: /進入/ })).toBeTruthy());
    fireEvent.click(r.getByRole("button", { name: /進入/ }));
    await waitFor(() => expect(r.container.querySelector(".usage-toast")).toBeTruthy());
    expect(r.container.querySelector(".journey")!.className).toContain("toasting");
  });

  it("沒 toast 就不讓位", async () => {
    const r = render(<MemoryRouter initialEntries={["/"]}><Routes><Route path="/" element={<Journey />} /></Routes></MemoryRouter>);
    await waitFor(() => expect(r.getByRole("button", { name: /進入/ })).toBeTruthy());
    fireEvent.click(r.getByRole("button", { name: /進入/ }));
    await waitFor(() => expect(r.container.querySelector(".field")).toBeTruthy());
    expect(r.container.querySelector(".journey")!.className).not.toContain("toasting");
  });
});
