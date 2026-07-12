import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";

const AGG = {
  slug: "s02", empty: false,
  phases: {
    analyst: { input: 100, output: 50, cache_creation: 200, cache_read: 900, cost_usd: 0.42, turns: 1 },
    criticizer: { input: 60, output: 40, cache_creation: 100, cache_read: 300, cost_usd: 0.38, turns: 1 },
    discuss: { input: 80, output: 120, cache_creation: 0, cache_read: 1200, cost_usd: 0.60, turns: 3 },
  },
  total: { input: 240, output: 210, cache_creation: 300, cache_read: 2400, cost_usd: 1.40 },
  cache_read_ratio: 0.8767, retry_cost_usd: 0.15, retry_count: 1,
};

const getUsage = vi.fn();
vi.mock("../src/data/client", () => ({ getUsage: (s: string) => getUsage(s) }));
import UsagePanel from "../src/journey/UsagePanel";

beforeEach(() => {
  vi.clearAllMocks();
  // 關動畫 → 確定性顯示終值
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true }));
});

describe("UsagePanel", () => {
  it("渲染三節、每格與金額、cache/重試", async () => {
    getUsage.mockResolvedValue(AGG);
    const { getByText, container } = render(<UsagePanel slug="s02" />);
    await waitFor(() => expect(getByText("花了多少")).toBeTruthy());
    expect(getByText("$1.40")).toBeTruthy();
    expect(getByText("花在哪格")).toBeTruthy();
    expect(getByText("discuss · 3 輪")).toBeTruthy();
    expect(getByText("$0.42")).toBeTruthy();
    expect(getByText("效率")).toBeTruthy();
    expect(getByText("1 次 · $0.15")).toBeTruthy();
    // 三個 phase 各一根長條
    expect(container.querySelectorAll(".prow").length).toBe(3);
  });

  it("空態顯示提示", async () => {
    getUsage.mockResolvedValue({ slug: "s02", empty: true, phases: {}, total: { input:0,output:0,cache_creation:0,cache_read:0,cost_usd:0 }, cache_read_ratio: 0, retry_cost_usd: 0, retry_count: 0 });
    const { getByText } = render(<UsagePanel slug="s02" />);
    await waitFor(() => expect(getByText(/尚無用量/)).toBeTruthy());
  });
});
