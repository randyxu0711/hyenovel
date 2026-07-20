import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor, fireEvent } from "@testing-library/react";
import type { IndexEntry } from "../src/types";
import { usageLayout, ringRadii } from "../src/lib/camera";

const ALL = {
  empty: false,
  total: { input: 16, output: 29540, cache_creation: 84785, cache_read: 207516, cost_usd: 4.78 },
  phases: {
    analyst: { input: 8, output: 20000, cache_creation: 50000, cache_read: 150000, cost_usd: 2.71, turns: 6 },
    criticizer: { input: 5, output: 8000, cache_creation: 30000, cache_read: 50000, cost_usd: 1.62, turns: 4 },
    discuss: { input: 3, output: 1540, cache_creation: 4785, cache_read: 7516, cost_usd: 0.45, turns: 9 },
  },
  retry_cost_usd: 0.61, retry_count: 2, duration_ms: 2040000, cache_read_ratio: 0.71,
  stories: [
    { slug: "s02", cost_usd: 1.18, tokens: 400000, runs: 2, retry_count: 1, last_run_cost_usd: 0.62 },
    { slug: "s07", cost_usd: 1.02, tokens: 321857, runs: 1, retry_count: 1, last_run_cost_usd: 1.02 },
    { slug: "s06", cost_usd: 0.79, tokens: 240000, runs: 1, retry_count: 0, last_run_cost_usd: 0.79 },
  ],
};

const ENTRIES = [
  { slug: "s02", title: "鬣狗的傷春悲秋", nodes: 38, has_viz: true, has_feedback: true },
  { slug: "s07", title: "長夜", nodes: 33, has_viz: true, has_feedback: true },
  { slug: "s06", title: "犁過亡者的骨骸", nodes: 28, has_viz: true, has_feedback: true },
] as IndexEntry[];

const getUsageAll = vi.fn();
vi.mock("../src/data/client", () => ({
  getUsageAll: () => getUsageAll(),
  getViz: () => Promise.resolve(null),
}));
import UsageMap, { slots } from "../src/journey/UsageMap";

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true }));   // 關動畫 → 終值
});

const setup = (all: unknown = ALL, onPick = vi.fn()) => {
  getUsageAll.mockResolvedValue(all);
  return {
    onPick,
    ...render(<UsageMap entries={ENTRIES} ordered={["s02", "s07", "s06"]} onPick={onPick} onClose={vi.fn()} />),
  };
};

describe("UsageMap", () => {
  it("中心是總計", async () => {
    const { getByText } = setup();
    await waitFor(() => expect(getByText("$4.78")).toBeTruthy());
    expect(getByText(/3 篇/)).toBeTruthy();
  });

  it("每篇一顆星,大小依花費(面積正比,最貴的最大)", async () => {
    const { container } = setup();
    await waitFor(() => expect(container.querySelectorAll(".ustar").length).toBe(3));
    const r = (slug: string) => {
      const el = container.querySelector(`.ustar[data-slug="${slug}"] .udot`) as HTMLElement;
      return parseFloat(el.style.width);
    };
    expect(r("s02")).toBeGreaterThan(r("s07"));    // $1.18 > $1.02
    expect(r("s07")).toBeGreaterThan(r("s06"));    // $1.02 > $0.79
  });

  it("年輪 = 重跑次數;暖紅疤 = 機器重試過", async () => {
    const { container } = setup();
    await waitFor(() => expect(container.querySelectorAll(".ustar").length).toBe(3));
    const rings = (slug: string) =>
      container.querySelectorAll(`.ustar[data-slug="${slug}"] .uring`).length;
    expect(rings("s02")).toBe(2);                  // 重跑 2 次 → 兩圈年輪
    expect(rings("s07")).toBe(1);
    expect(container.querySelector('.ustar[data-slug="s07"] .uscar')).toBeTruthy();  // 重試過
    expect(container.querySelector('.ustar[data-slug="s06"] .uscar')).toBeNull();    // 乾淨
  });

  it("每節點單價:分子是最後一次 critique 的錢,分母是最新那具骨的節點數", async () => {
    const { getByText } = setup();
    // s07:1.02 / 33 = 0.031
    await waitFor(() => expect(getByText(/33 節點 · \$0\.031 \/ 節點/)).toBeTruthy());
    // s02 重跑過:用 last_run 0.62 / 38 = 0.016(不是累計的 1.18/38=0.031)
    expect(getByText(/38 節點 · \$0\.016 \/ 節點/)).toBeTruthy();
  });

  it("點星回報 slug(→ 進該篇用量)", async () => {
    const { container, onPick } = setup();
    await waitFor(() => expect(container.querySelectorAll(".ustar").length).toBe(3));
    fireEvent.click(container.querySelector('.ustar[data-slug="s07"]')!);
    expect(onPick).toHaveBeenCalledWith("s07");
  });

  it("星塵:階段、重試、時數、cache", async () => {
    const { getByText } = setup();
    await waitFor(() => expect(getByText("$2.71")).toBeTruthy());     // analyst
    expect(getByText("$1.62")).toBeTruthy();                          // criticizer
    expect(getByText(/9 輪/)).toBeTruthy();                           // discuss 輪數
    expect(getByText(/佔 9%/)).toBeTruthy();                          // 討論比例 0.45/4.78
    expect(getByText("$0.61")).toBeTruthy();                          // 重試燒掉
    expect(getByText("34 分鐘")).toBeTruthy();                        // 2040000ms
    expect(getByText("71%")).toBeTruthy();                            // cache
  });

  it("還沒討論過 → 不秀 0%,秀零態", async () => {
    const noDiscuss = { ...ALL, phases: { analyst: ALL.phases.analyst, criticizer: ALL.phases.criticizer } };
    const { getByText, queryByText } = setup(noDiscuss);
    await waitFor(() => expect(getByText("$2.71")).toBeTruthy());
    expect(getByText(/尚未討論過/)).toBeTruthy();
    expect(queryByText(/佔 0%/)).toBeNull();
  });

  it("完全沒用量 → 空態", async () => {
    const { getByText } = setup({
      empty: true, total: { input: 0, output: 0, cache_creation: 0, cache_read: 0, cost_usd: 0 },
      phases: {}, retry_cost_usd: 0, retry_count: 0, duration_ms: 0, cache_read_ratio: 0, stories: [],
    });
    await waitFor(() => expect(getByText(/還沒有用量/)).toBeTruthy());
  });

  it("星落在目錄槽位(ordered 順序),不依花費排位", async () => {
    const { container } = setup();
    await waitFor(() => expect(container.querySelectorAll(".ustar").length).toBe(3));
    const { pts } = usageLayout(3, window.innerWidth, window.innerHeight);
    const at = (slug: string) => {
      const el = container.querySelector(`.ustar[data-slug="${slug}"]`) as HTMLElement;
      return { x: parseFloat(el.style.left), y: parseFloat(el.style.top) };
    };
    expect(at("s07").x).toBeCloseTo(pts[1].x);   // ordered[1],即使它不是最貴
    expect(at("s07").y).toBeCloseTo(pts[1].y);
  });

  it("軌道畫真的:環數 = ringRadii(槽位數)", async () => {
    const { container } = setup();
    await waitFor(() => expect(container.querySelectorAll(".umap-orbits ellipse").length)
      .toBe(ringRadii(3).length));
  });

  it("冷星:有槽位沒用量 → 餘燼點;完成的可點進、未完成的不可導航(T8 政策)", async () => {
    const entries = [...ENTRIES,
      { slug: "s01", title: "舊完成篇", nodes: 20, has_viz: true, has_feedback: true },
      { slug: "s99", title: "孕育中", nodes: 0 }] as IndexEntry[];
    const onPick = vi.fn();
    getUsageAll.mockResolvedValue(ALL);
    const { container } = render(<UsageMap entries={entries}
      ordered={["s02", "s07", "s06", "s01", "s99"]} onPick={onPick} onClose={vi.fn()} />);
    await waitFor(() => expect(container.querySelectorAll(".ustar.cold").length).toBe(2));
    expect(container.querySelectorAll(".ustar").length).toBe(5);   // 槽位一一對應,冷星不消失
    fireEvent.click(container.querySelector('.ustar.cold[data-slug="s01"]')!);
    expect(onPick).toHaveBeenCalledWith("s01");
    fireEvent.click(container.querySelector('.ustar.cold[data-slug="s99"]')!);
    expect(onPick).not.toHaveBeenCalledWith("s99");
  });

  it("帳本孤兒(有用量、目錄已刪)排在既有槽位之後,不搶位", () => {
    expect(slots(["a", "b"], [{ slug: "b" }, { slug: "zz" }])).toEqual(["a", "b", "zz"]);
  });

  it("星多到 zoom 低於可讀地板 → .umap.tight(標籤退 hover)", async () => {
    const many = Array.from({ length: 22 }, (_, i) => `m${i}`);
    getUsageAll.mockResolvedValue({ ...ALL,
      stories: many.map(slug => ({ slug, cost_usd: 0.5, tokens: 1, runs: 1, retry_count: 0, last_run_cost_usd: 0.5 })) });
    const { container } = render(<UsageMap entries={[]} ordered={many}
      onPick={vi.fn()} onClose={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".umap.tight")).toBeTruthy());
    // 3 篇時(既有 setup)不 tight
    const { container: few } = setup();
    await waitFor(() => expect(few.querySelectorAll(".ustar").length).toBe(3));
    expect(few.querySelector(".umap.tight")).toBeNull();
  });
});
