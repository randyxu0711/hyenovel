import { describe, it, expect, vi, beforeEach, afterEach, type MockInstance } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { api, DashError, type UsageReport, type UsageWork } from "../src/dash/api";
import { setLang } from "../src/dash/i18n";
import UsagePage from "../src/dash/UsagePage";

const work = (i: number, over: Partial<UsageWork> = {}): UsageWork => ({
  story_id: i, slug: `s${i}`, title: `作品${i}`, archived: false, tokens: 1000 - i, partial: false,
  by_category: { analysis: 600 - i, chat: 400 }, versions: [], ...over,
});
const group = { first_at: 1_700_000_000, last_at: 1_700_000_000, n: 3, avg: 100, thinking: 20, ms_median: 9800,
  current: false, delta: null, recorded: true };

const report = (over: Partial<UsageReport> = {}): UsageReport => ({
  as_of: 1_700_000_000,
  quota: { at: 1_700_000_000, five_hour: { utilization: 0.34, resets_at: 1_700_003_600 },
           seven_day: { utilization: 0.88, resets_at: 1_700_300_000 } },
  total: { tokens: 1_080_000, partial: true },
  categories: [
    { id: "analysis", n: 6, tokens: 492_000, partial: false, avg: 82_000, share: 0.46 },
    { id: "chat", n: 84, tokens: 504_000, partial: true, avg: 6040, share: 0.47 },
    { id: "character", n: 3, tokens: 48_000, partial: false, avg: null, share: 0.04 },
  ],
  unused_share: 0.08,
  works: [work(1, {
    archived: true,
    versions: [{ n: 1, tokens: 78_000, partial: false, analyzed: true }, { n: 2, tokens: 0, partial: false, analyzed: true },
               { n: 3, tokens: 0, partial: false, analyzed: false }],
  }), ...Array.from({ length: 11 }, (_, i) => work(i + 2))],
  unbound: { tokens: 60_000, partial: false, by_category: { chat: 56_000, upkeep: 4000 } },
  compare: {
    config: [
      { ...group, kind: "chat", prompt_fp: "19c04ea9b1c2", runner: "claude-cli", model: "claude-opus-5-5", effort: "medium",
        current: true, delta: { avg: 0.14, thinking: -0.11, ms: null } },
      { ...group, kind: "chat", prompt_fp: "e52d7b1aaaaa", runner: "claude-cli", model: "claude-opus-5-5", effort: "low" },
      { ...group, kind: "chat", prompt_fp: "0000000fffff", runner: null, model: null, effort: null, recorded: false },
    ],
    character: [
      { ...group, character_id: "hyena", character_v: 4, name: { "zh-Hant": "鬣狗", en: "Hyena" }, current: true,
        delta: { avg: -0.11, thinking: null, ms: null } },
      { ...group, character_id: null, character_v: null, name: null, recorded: false },
    ],
  },
  running: 0,
  completeness: { partial: 2, unknown: 1 },
  ...over,
});

let usage: MockInstance<typeof api.usage>;
beforeEach(() => {
  setLang("zh-Hant");
  usage = vi.spyOn(api, "usage").mockResolvedValue(report());
});
afterEach(() => vi.restoreAllMocks());

const mount = async () => {
  const r = render(<div className="dash"><UsagePage /></div>);
  await screen.findByText("使用額度");
  return r;
};

describe("用量頁", () => {
  it("額度:≥80% 的列帶 data-warn 並改說接近上限", async () => {
    await mount();
    const seven = screen.getByRole("meter", { name: "七日額度" });
    expect(seven.closest(".use-gauge")!.hasAttribute("data-warn")).toBe(true);
    expect(screen.getAllByText("已使用 88%，接近上限").length).toBeGreaterThan(0);
    expect(screen.getByRole("meter", { name: "五小時額度" }).closest(".use-gauge")!.hasAttribute("data-warn")).toBe(false);
    expect(screen.getByText(/^資料截至/)).toBeTruthy();
  });
  it("額度沒有資料:說明句", async () => {
    usage.mockResolvedValue(report({ quota: null }));
    await mount();
    expect(screen.getByText("尚未取得額度資訊。進行一次陪讀對話後即會顯示。")).toBeTruthy();
    expect(screen.queryByRole("meter")).toBeNull();
  });
  it("期間切換重打 API;預設近 7 日", async () => {
    await mount();
    expect(usage).toHaveBeenLastCalledWith("7", expect.any(AbortSignal));
    const seg = screen.getByRole("group", { name: "期間" });
    fireEvent.click(within(seg).getByRole("button", { name: "近 30 日" }));
    await waitFor(() => expect(usage).toHaveBeenLastCalledWith("30", expect.any(AbortSignal)));
    expect(within(seg).getByRole("button", { name: "近 30 日" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(within(seg).getByRole("button", { name: "全部" }));
    await waitFor(() => expect(usage).toHaveBeenLastCalledWith("all", expect.any(AbortSignal)));
  });
  it("期間合計:部分用量帶 ≥", async () => {
    await mount();
    expect(screen.getByText("共 ≥108.0 萬 token")).toBeTruthy();
  });
  it("用途列:用量、占比、單次平均;部分用量帶 ≥,平均缺值顯示 —", async () => {
    await mount();
    const table = screen.getByRole("table", { name: "用途" });
    const row = (name: string) => within(table).getByRole("row", { name: new RegExp(name) });
    expect(within(row("讀稿分析")).getAllByRole("cell").map(c => c.textContent)).toEqual(["49.2 萬", "46%", "8.2 萬"]);
    expect(within(row("陪讀對話")).getAllByRole("cell")[0].textContent).toBe("≥50.4 萬");
    expect(within(row("建立角色")).getAllByRole("cell")[2].textContent).toBe("—");
    expect(screen.getByText("其中未使用部分 8%")).toBeTruthy();
  });
  it("作品:前 10 篇 + 其餘按鈕,按了展開;未綁作品列在最後;封存帶記號", async () => {
    await mount();
    expect(screen.queryByText("作品12")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "其餘 2 篇" }));
    expect(screen.getByText("作品12")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /其餘/ })).toBeNull();
    const items = screen.getByText("作品1").closest("ul")!.querySelectorAll(":scope > li");
    expect(items[items.length - 1].textContent).toContain("未綁作品的對話");
    expect(within(screen.getByText("作品1").closest("summary")!).getByText("已封存")).toBeTruthy();
  });
  it("作品展開:用途分項與各版直條(未分析虛線框、有分析沒用量顯示 —)", async () => {
    await mount();
    const details = screen.getByText("作品1").closest("details")!;
    fireEvent.click(details.querySelector("summary")!);
    const vers = within(details).getAllByRole("listitem");
    expect(vers.map(v => v.textContent)).toEqual(["7.8 萬第 1 版", "—第 2 版", "未分析第 3 版"]);
    expect(vers[2].hasAttribute("data-none")).toBe(true);
    expect(within(details).getByText("讀稿分析")).toBeTruthy();
  });
  it("比較:預設收合;目前列帶增減;未記錄不標目前", async () => {
    await mount();
    const cmp = screen.getByText("比較").closest("details")!;
    expect(cmp.open).toBe(false);
    expect(within(cmp).getByText("比較涵蓋全部期間")).toBeTruthy();
    const prompt = within(cmp).getByRole("table", { name: "依提示版本" });
    const rows = within(prompt).getAllByRole("row").slice(1);
    expect(rows[0].textContent).toContain("陪讀回覆目前");
    expect(rows[0].textContent).toContain("19c04ea，");
    expect(rows[0].textContent).toContain("claude-opus-5-5medium");
    expect(within(rows[0]).getByText("+14%")).toBeTruthy();
    expect(within(rows[0]).getByText("−11%")).toBeTruthy();
    expect(rows[1].textContent).not.toContain("目前");
    expect(rows[2].textContent).toContain("未記錄");
    expect(rows[2].textContent).not.toContain("目前");
    const comp = within(cmp).getByRole("table", { name: "依讀伴" });
    const crow = within(comp).getAllByRole("row").slice(1);
    expect(crow[0].textContent).toContain("鬣狗目前第 4 版");
    expect(crow[1].textContent).toContain("未記錄");
    expect(crow[1].textContent).not.toContain("目前");
  });
  it("頁底:有部分或不明用量才顯示", async () => {
    const { unmount } = await mount();
    expect(screen.getByText("另有 3 次呼叫未取得完整用量，上列數字為下限。")).toBeTruthy();
    unmount();
    usage.mockResolvedValue(report({ completeness: { partial: 0, unknown: 0 } }));
    await mount();
    expect(screen.queryByText(/另有/)).toBeNull();
  });
  it("期間沒有用量:說明句,額度照常", async () => {
    usage.mockResolvedValue(report({ total: { tokens: 0, partial: false }, categories: [], works: [], unbound: null,
                                     completeness: { partial: 0, unknown: 0 } }));
    await mount();
    expect(screen.getByText("此期間沒有用量紀錄。")).toBeTruthy();
    expect(screen.getByRole("meter", { name: "七日額度" })).toBeTruthy();
    expect(screen.queryByText("用途")).toBeNull();
  });
  it("den 是舊程式(404):帳本未建立", async () => {
    usage.mockRejectedValue(new DashError(404, "unknown"));
    render(<UsagePage />);
    expect(await screen.findByText("用量帳本尚未建立，重新啟動 den 後即可使用。")).toBeTruthy();
  });
  it("有呼叫進行中:另起一句說明", async () => {
    usage.mockResolvedValue(report({ running: 2 }));
    await mount();
    expect(screen.getByText("另有 2 次呼叫進行中，未列入。")).toBeTruthy();
  });
  it("其他錯誤:無法讀取", async () => {
    usage.mockRejectedValue(new DashError(500, "unknown"));
    render(<UsagePage />);
    expect(await screen.findByText("無法讀取用量資料。")).toBeTruthy();
  });
});
