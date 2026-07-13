import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Journey from "../src/journey/Journey";
import index from "./fixtures/index.json";
import viz from "./fixtures/viz.json";

const USAGE_ALL = {
  empty: false,
  total: { input: 16, output: 29540, cache_creation: 84785, cache_read: 207516, cost_usd: 1.02 },
  phases: { analyst: { input: 8, output: 20000, cache_creation: 50000, cache_read: 150000, cost_usd: 0.75, turns: 2 } },
  retry_cost_usd: 0.37, retry_count: 1, duration_ms: 575642, cache_read_ratio: 0.71,
  stories: [{ slug: (index as { stories: { slug: string }[] }).stories[0].slug,
              cost_usd: 1.02, tokens: 321857, runs: 1, retry_count: 1, last_run_cost_usd: 1.02 }],
};

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    clearRect: vi.fn(), beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(),
  } as unknown as CanvasRenderingContext2D);
  // framer-motion(Overview 用)會呼叫 addListener → stub 得完整,不能只給 matches
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
    matches: true, addListener: vi.fn(), removeListener: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
  }));
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    const body = url.includes("/api/usage") ? USAGE_ALL
      : url.includes("index.json") ? index
      : url.includes("viz.json") ? viz : null;
    if (body) return Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);
    return Promise.resolve({ ok: true, text: () => Promise.resolve("　　原文一段。") } as Response);
  }));
});

const app = () => render(
  <MemoryRouter initialEntries={["/"]}>
    <Routes>
      <Route path="/" element={<Journey />} />
      <Route path="/story/:slug" element={<Journey />} />
    </Routes>
  </MemoryRouter>,
);

async function toCatalog(r: ReturnType<typeof app>) {
  await waitFor(() => expect(r.getByText(/進入/)).toBeTruthy());
  fireEvent.click(r.getByText(/進入/));
  await waitFor(() => expect(r.container.querySelector(".field")).toBeTruthy());
}

describe("用量入口", () => {
  it("目錄層角落有低調入口,帶累計總額", async () => {
    const r = app();
    await toCatalog(r);
    await waitFor(() => expect(r.container.querySelector(".usage-entry")).toBeTruthy());
    expect(r.getByText("$1.02")).toBeTruthy();
  });

  it("點入口 → 開出用量星圖", async () => {
    const r = app();
    await toCatalog(r);
    await waitFor(() => expect(r.container.querySelector(".usage-entry")).toBeTruthy());
    fireEvent.click(r.container.querySelector(".usage-entry")!);
    await waitFor(() => expect(r.getByTestId("usage-map")).toBeTruthy());
  });

  // toast 跟入口同住右下角(toast 340px 寬、z-index 高)→ 撞上限時入口會被整個蓋掉。
  // 讓 journey 掛上 toasting,CSS 據此把入口(和星圖右下那格)抬到 toast 上方。
  it("用量上限 toast 在場時,右下角讓位(journey 掛 toasting)", async () => {
    localStorage.setItem("hy:usageLimit", String(Math.floor(Date.now() / 1000) + 3600));
    const r = app();
    await toCatalog(r);
    await waitFor(() => expect(r.container.querySelector(".usage-toast")).toBeTruthy());
    expect(r.container.querySelector(".journey")!.className).toContain("toasting");
    expect(r.container.querySelector(".usage-entry")).toBeTruthy();   // 兩個都還在
  });

  it("沒 toast 就不讓位", async () => {
    const r = app();
    await toCatalog(r);
    await waitFor(() => expect(r.container.querySelector(".usage-entry")).toBeTruthy());
    expect(r.container.querySelector(".journey")!.className).not.toContain("toasting");
  });

  // .nascent(z-index 42)住畫面正中,比 .umap(40)高 → 星圖開著時它壓在中央總額上還能點。
  it("星圖開著時,中心的新增故事入口收起", async () => {
    const r = app();
    await toCatalog(r);
    await waitFor(() => expect(r.container.querySelector(".nascent")).toBeTruthy());
    fireEvent.click(r.container.querySelector(".usage-entry")!);
    await waitFor(() => expect(r.getByTestId("usage-map")).toBeTruthy());
    expect(r.container.querySelector(".nascent")).toBeNull();
    // 關掉星圖 → 入口回來
    fireEvent.click(r.container.querySelector(".umap-x")!);
    await waitFor(() => expect(r.container.querySelector(".nascent")).toBeTruthy());
  });

  it("點星 → 進該篇,且直接開在用量 tab", async () => {
    const slug = (index as { stories: { slug: string }[] }).stories[0].slug;
    const r = app();
    await toCatalog(r);
    await waitFor(() => expect(r.container.querySelector(".usage-entry")).toBeTruthy());
    fireEvent.click(r.container.querySelector(".usage-entry")!);
    await waitFor(() => expect(r.container.querySelector(`.ustar[data-slug="${slug}"]`)).toBeTruthy());
    fireEvent.click(r.container.querySelector(`.ustar[data-slug="${slug}"]`)!);
    // 進了單篇,而且第三顆 tab(用量)是開著的
    await waitFor(() => expect(r.container.querySelector(".sb")).toBeTruthy());
    await waitFor(() => {
      const tabs = r.container.querySelectorAll(".sb-textabs button");
      expect(tabs[2].className).toContain("on");
    });
  });
});
