import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import Catalog from "../src/journey/Catalog";
import type { IndexEntry, Gestation } from "../src/types";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() =>
    Promise.resolve({ ok: false, json: () => Promise.resolve({}) } as Response)));
});

// 完整 IndexEntry(12 欄必填);has_viz 預設 true;已完成故事 status=done、resumable=false、reason=null
const mk = (slug: string, title: string, has_viz = true): IndexEntry =>
  ({ slug, title, synopsis: "", nodes: 0, edges: 0, has_feedback: false, has_viz, updated: "",
     status: "done", stage: "done", resumable: false, reason: null });

const entries: IndexEntry[] = [mk("born", "已生")];
const noGest: Map<string, Gestation> = new Map();

describe("Catalog", () => {
  it("每篇一個 story 元素", () => {
    const { getAllByTestId, getByText } = render(
      <Catalog entries={entries} ordered={["born"]} gestations={noGest} onPick={() => {}} onCancel={() => {}} />);
    expect(getAllByTestId("story").length).toBe(1);
    expect(getByText("已生")).toBeTruthy();
  });
  it("空 ordered 顯示空狀態", () => {
    const { getByText } = render(
      <Catalog entries={[]} ordered={[]} gestations={noGest} onPick={() => {}} onCancel={() => {}} />);
    expect(getByText(/還沒有故事/)).toBeTruthy();
  });
  it("誕生用 Skeleton(bone-ph 佔位),孕育無資料時用分子雲塌縮 + 階段詞", () => {
    const g: Map<string, Gestation> = new Map([["egg", { step: 2, status: "running", title: "胚胎" }]]);
    const { container, getByText } = render(
      <Catalog entries={entries} ordered={["born", "egg"]} gestations={g} onPick={() => {}} onCancel={() => {}} />);
    expect(container.querySelector('[data-testid="collapsing"]')).toBeTruthy(); // egg
    expect(container.querySelector(".bone-ph")).toBeTruthy();                   // born(viz 未載入 → 佔位)
    expect(getByText("秤出輕重")).toBeTruthy();     // step2 = criticizer 跑中,那正是它在做的事
  });
  it("點孕育星不觸發 onPick;點誕生星觸發 onPick", () => {
    const g: Map<string, Gestation> = new Map([["egg", { step: 1, status: "running", title: "胚胎" }]]);
    const onPick = vi.fn();
    const { getAllByTestId } = render(
      <Catalog entries={entries} ordered={["born", "egg"]} gestations={g} onPick={onPick} onCancel={() => {}} />);
    const [bornEl, eggEl] = getAllByTestId("story");
    eggEl.click(); expect(onPick).not.toHaveBeenCalled();
    bornEl.click(); expect(onPick).toHaveBeenCalledWith("born");
  });
  it("誕生確認波:只有 confirming 那篇長出波(三層環)", () => {
    const { getAllByTestId } = render(
      <Catalog entries={[mk("born", "已生"), mk("other", "另一篇")]} ordered={["born", "other"]}
        gestations={noGest} confirming="born" onPick={() => {}} onCancel={() => {}} />);
    const [bornEl, otherEl] = getAllByTestId("story");
    expect(bornEl.querySelectorAll(".bwave i").length).toBe(3);
    expect(otherEl.querySelector(".bwave")).toBeNull();
  });
  it("誕生確認波:還在孕育的那篇即使被標 confirming 也不放(波確認的是骨已在場)", () => {
    const g: Map<string, Gestation> = new Map([["egg", { step: 4, status: "running", title: "胚胎" }]]);
    const { getAllByTestId } = render(
      <Catalog entries={[]} ordered={["egg"]} gestations={g} confirming="egg"
        onPick={() => {}} onCancel={() => {}} />);
    expect(getAllByTestId("story")[0].querySelector(".bwave")).toBeNull();
  });
  it("階段詞對齊後端那格實際在幹嘛,不是跑完第幾格", () => {
    const view = (step: number) => (
      <Catalog entries={[]} ordered={["egg"]} onPick={() => {}} onCancel={() => {}}
        gestations={new Map([["egg", { step, status: "running", title: "胚胎" }]])} />);
    const { getByText, queryByText, rerender } = render(view(1));
    expect(getByText("凝聚"), "step1 = analyst 跑中,真的還沒資料").toBeTruthy();
    rerender(view(2));
    expect(getByText("秤出輕重"), "step2 = criticizer 跑中,那正是它在做的事").toBeTruthy();
    expect(queryByText("長出骨架"), "「長出骨架」不是一格,是 step1→2 的轉場瞬間").toBeNull();
  });
  it("孕育中 vizReady:塌縮換成真骨(早出 viz 落檔 → 不再有任何假骨)", () => {
    const g = (vizReady?: boolean): Map<string, Gestation> =>
      new Map([["egg", { step: 2, status: "running", title: "胚胎", vizReady }]]);
    const { container, rerender } = render(
      <Catalog entries={[]} ordered={["egg"]} gestations={g()} onPick={() => {}} onCancel={() => {}} />);
    expect(container.querySelector('[data-testid="collapsing"]'), "還沒資料就該是塌縮").toBeTruthy();

    rerender(
      <Catalog entries={[]} ordered={["egg"]} gestations={g(true)} onPick={() => {}} onCancel={() => {}} />);
    expect(container.querySelector('[data-testid="collapsing"]'), "有資料了還在塌縮").toBeNull();
    expect(container.querySelector(".bone-ph"), "該換成真骨(viz 未載入 → 佔位)").toBeTruthy();
  });
  it("停拍 paused:標 .paused,點續跑觸發 onResume;點星身不進單篇(onPick 不動)", () => {
    const g: Map<string, Gestation> = new Map([["egg", { step: 2, status: "paused", title: "胚胎", vizReady: true }]]);
    const onPick = vi.fn(), onResume = vi.fn();
    const { container } = render(
      <Catalog entries={[]} ordered={["egg"]} gestations={g} onPick={onPick} onCancel={() => {}} onResume={onResume} />);
    const el = container.querySelector<HTMLElement>('[data-testid="story"]')!;
    expect(el.className).toContain("paused");
    el.querySelector<HTMLButtonElement>(".gest-resume")!.click();
    expect(onResume).toHaveBeenCalledWith("egg", "胚胎");
    el.click();
    expect(onPick).not.toHaveBeenCalled();
  });
  it("停拍 failed:標 .failed + 原因翻成友善字(gate → 未通過檢核)", () => {
    const g: Map<string, Gestation> = new Map([["egg", { step: 2, status: "failed", title: "胚胎", vizReady: true, reason: "gate" }]]);
    const { container, getByText } = render(
      <Catalog entries={[]} ordered={["egg"]} gestations={g} onPick={() => {}} onCancel={() => {}} />);
    expect(container.querySelector('[data-testid="story"]')!.className).toContain("failed");
    expect(getByText(/未通過檢核/)).toBeTruthy();
  });
  it("重新分析:完整星才有鈕,且二次確認——確定才觸發 onReanalyze", () => {
    const onReanalyze = vi.fn();
    const complete: IndexEntry = { ...mk("done1", "成篇"), has_feedback: true, has_viz: true };
    const { container, getByText } = render(
      <Catalog entries={[complete]} ordered={["done1"]} gestations={noGest}
        onPick={() => {}} onCancel={() => {}} onReanalyze={onReanalyze} />);
    fireEvent.click(container.querySelector<HTMLButtonElement>(".reanalyze")!);
    expect(onReanalyze, "第一下只進確認態,不觸發").not.toHaveBeenCalled();
    fireEvent.click(getByText("確定"));
    expect(onReanalyze).toHaveBeenCalledWith("done1", "成篇");
  });
  it("重新分析:不完整故事(mk 的 has_feedback=false)不給鈕", () => {
    const { container } = render(
      <Catalog entries={[mk("v", "只有viz")]} ordered={["v"]} gestations={noGest}
        onPick={() => {}} onCancel={() => {}} onReanalyze={() => {}} />);
    expect(container.querySelector(".reanalyze")).toBeNull();
  });
  it("同一 slug 從孕育轉誕生:renderer 由塌縮換成 Skeleton 佔位", () => {
    const g: Map<string, Gestation> = new Map([["x", { step: 3, status: "running", title: "x" }]]);
    const { container, rerender } = render(
      <Catalog entries={[]} ordered={["x"]} gestations={g} onPick={() => {}} onCancel={() => {}} />);
    expect(container.querySelector('[data-testid="collapsing"]')).toBeTruthy();
    rerender(
      <Catalog entries={[mk("x", "x")]} ordered={["x"]} gestations={new Map()} onPick={() => {}} onCancel={() => {}} />);
    expect(container.querySelector('[data-testid="collapsing"]')).toBeNull();
    expect(container.querySelector(".bone-ph")).toBeTruthy();
  });
});
