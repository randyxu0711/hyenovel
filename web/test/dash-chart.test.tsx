import { describe, it, expect, vi, beforeEach } from "vitest";
import { useEffect } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import ChartTab from "../src/dash/ChartTab";
import type { Span, WorkMap } from "../src/dash/api";
import { setLang } from "../src/dash/i18n";
import { LinksProvider, useLinks } from "../src/dash/links";
import type { Mark } from "../src/dash/Paper";
import { CharactersProvider, makeCharacters } from "../src/dash/useCharacters";
import { hyena, buffalo } from "./dash-fixtures";

function PaperSpy({ on }: { on: (s: Span) => void }) {
  const { registerPaper } = useLinks();
  useEffect(() => registerPaper(on), [registerPaper, on]);
  return null;
}
const INT = [0.2, 0.7, 0.4, null, 0.9, 0.1, 0.5, 0.3];
const beats = INT.map((intensity, i) => ({ id: `b${i}`, label: `節拍${i}`, intensity, span: { quote: `q${i}`, start: i * 10, end: i * 10 + 5 } }));
const map = (o: Partial<WorkMap> = {}): WorkMap => ({
  version: 2, analysis_version: 2, notes_version: null, beats, motifs: [], notes: null, drift: null, ...o,
});
function mount(m: WorkMap | null, marks: Mark[] = [], on = vi.fn(), error: string | null = null, ob: string | null = null, onOb = vi.fn()) {
  const r = render(<CharactersProvider value={makeCharacters([hyena, buffalo], "hyena")}><LinksProvider>
    <PaperSpy on={on} /><ChartTab map={m} marks={marks} error={error} ob={ob} onOb={onOb} />
  </LinksProvider></CharactersProvider>);
  return { ...r, on };
}
const cols = (c: HTMLElement) => [...c.querySelectorAll<HTMLButtonElement>("button.dash-mcol")];

beforeEach(() => setLang("zh-Hant"));

describe("結構圖分頁", () => {
  it("drift null → 不顯示失根資訊", () => {
    const { container } = mount(map());
    expect(container.textContent).not.toMatch(/找不到了|都還找得到/);
  });
  it("有失根 → 顯示 2/3 並列出失根觀察", () => {
    const { container } = mount(map({ drift: { total: 3, lost: 2, orphaned: [{ id: "m1", type: "motif", label: "海" }] } }));
    expect(container.textContent).toContain("2/3");
    expect(container.textContent).toContain("找不到根據");
    expect(screen.getByText("海")).toBeTruthy();
  });
  it("lost 為 0 → 不出聲", () => {
    const { container } = mount(map({ drift: { total: 3, lost: 0, orphaned: [] } }));
    expect(container.querySelector(".side-old")).toBeNull();
  });
  it("每個 beat 一欄熱區;折線一個節拍一點,高 = intensity;最高那欄 is-peak;段號用點陣字", () => {
    const { container } = mount(map());
    const cs = cols(container);
    expect(cs).toHaveLength(8);
    const pts = container.querySelector(".side-line polyline")!.getAttribute("points")!.split(" ").map(p => p.split(",").map(Number));
    expect(pts).toHaveLength(8);
    expect(pts.map(p => p[0])).toEqual([...pts.map(p => p[0])].sort((a, b) => a - b));
    expect(pts[4][1]).toBeLessThan(pts[1][1]);
    expect(pts[3][1]).toBeGreaterThan(pts[0][1]);
    expect(cs[1].getAttribute("aria-label")).toBe("第 2 段,張力 7");
    expect(cs.filter(c => c.classList.contains("is-peak"))).toEqual([cs[4]]);
    expect(cs[0].querySelector(".dash-dm")!.textContent).toBe("1");
  });
  it("只有一個節拍也畫得出線", () => {
    const { container } = mount(map({ beats: [beats[0]] }));
    expect(container.querySelector(".side-line polyline")!.getAttribute("points")!.split(" ")).toHaveLength(2);
  });
  it("點一欄 → 稿捲到那個節拍", () => {
    const { container, on } = mount(map());
    fireEvent.click(cols(container)[2]);
    expect(on).toHaveBeenCalledWith(beats[2].span);
  });
  it("沒有位置的節拍那欄不能點", () => {
    const { container } = mount(map({ beats: [{ id: "b0", label: "x", intensity: 0.5, span: null }] }));
    expect(cols(container)[0].disabled).toBe(true);
  });
  it("讀伴提過的段:段號下畫波浪線(跟稿上同一種記號),記最後一個痕跡的角色", () => {
    const marks: Mark[] = [
      { start: 11, end: 13, character: "hyena", id: "a" },
      { start: 12, end: 14, character: "buffalo", id: "b" },
    ];
    const { container } = mount(map(), marks);
    const cs = cols(container);
    expect(cs[1].querySelector<SVGElement>(".side-wave")!.dataset.who).toBe("buffalo");
    expect(cs[0].querySelector(".side-wave")).toBeNull();
  });
  it("意象列出標題與出現在哪幾段", () => {
    mount(map({ motifs: [{ id: "m1", label: "鞋", spans: [{ quote: "a", start: 41, end: 42 }, { quote: "b", start: 2, end: 3 }, { quote: "c", start: null, end: null }] }] }));
    expect(screen.getByRole("button", { name: /鞋/ })).toBeTruthy();
    expect(screen.getByText("第 1、5 段")).toBeTruthy();
  });
  it("這版對不到的意象:變淡不能按,不寫說明字", () => {
    mount(map({ motifs: [{ id: "m1", label: "鞋", spans: [{ quote: "a", start: null, end: null }] }] }));
    const b = screen.getByRole("button", { name: /鞋/ }) as HTMLButtonElement;
    expect(b.disabled).toBe(true);
    expect(b.textContent).toBe("鞋");
    expect(b.title).toBe("這一版的稿上對不到");
  });
  it("意象是切換鈕:按了選它、選中的再按 → 取消", () => {
    const shoe = { id: "m1", label: "鞋", spans: [{ quote: "a", start: 2, end: 3 }] };
    const onOb = vi.fn();
    const r = mount(map({ motifs: [shoe] }), [], vi.fn(), null, null, onOb);
    const b = () => screen.getByRole("button", { name: /鞋/ });
    expect(b().getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(b());
    expect(onOb).toHaveBeenLastCalledWith("m1");
    r.unmount();
    mount(map({ motifs: [shoe] }), [], vi.fn(), null, "m1", onOb);
    expect(b().getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(b());
    expect(onOb).toHaveBeenLastCalledWith(null);
  });
  it("沒分析 → 說還沒分析,沒有欄", () => {
    const { container } = mount(map({ analysis_version: null, beats: [] }));
    expect(screen.getByText(/還沒分析/)).toBeTruthy();
    expect(cols(container)).toHaveLength(0);
  });
  it("分析屬於別版 → 頂端「這是第 N 版的分析」", () => {
    mount(map({ analysis_version: 1 }));
    expect(screen.getByText("v1 的分析")).toBeTruthy();
  });
  it("對位資料抓不到:顯示錯誤,不停在載入中", () => {
    mount(null, [], vi.fn(), "den-down");
    expect(screen.getByText("連不上本機的 den,請確認它有在跑。")).toBeTruthy();
    expect(screen.queryByText("載入中……")).toBeNull();
  });
  it("同版就不提示", () => {
    mount(map());
    expect(screen.queryByText(/版的分析/)).toBeNull();
  });
});
