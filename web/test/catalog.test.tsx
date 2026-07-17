import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import Catalog from "../src/journey/Catalog";
import type { IndexEntry, Gestation } from "../src/types";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() =>
    Promise.resolve({ ok: false, json: () => Promise.resolve({}) } as Response)));
});

// 完整 IndexEntry(8 欄必填);has_viz 預設 true
const mk = (slug: string, title: string, has_viz = true): IndexEntry =>
  ({ slug, title, synopsis: "", nodes: 0, edges: 0, has_feedback: false, has_viz, updated: "" });

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
  it("誕生用 Skeleton(bone-ph 佔位),孕育用 GestatingStar + 階段詞", () => {
    const g: Map<string, Gestation> = new Map([["egg", { step: 2, status: "running", title: "胚胎" }]]);
    const { container, getByText } = render(
      <Catalog entries={entries} ordered={["born", "egg"]} gestations={g} onPick={() => {}} onCancel={() => {}} />);
    expect(container.querySelector('[data-testid="gestating"]')).toBeTruthy(); // egg
    expect(container.querySelector(".bone-ph")).toBeTruthy();                   // born(viz 未載入 → 佔位)
    expect(getByText("長出骨架")).toBeTruthy();                                  // step2 階段詞
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
  it("同一 slug 從孕育轉誕生:renderer 由 GestatingStar 換成 Skeleton 佔位", () => {
    const g: Map<string, Gestation> = new Map([["x", { step: 3, status: "running", title: "x" }]]);
    const { container, rerender } = render(
      <Catalog entries={[]} ordered={["x"]} gestations={g} onPick={() => {}} onCancel={() => {}} />);
    expect(container.querySelector('[data-testid="gestating"]')).toBeTruthy();
    rerender(
      <Catalog entries={[mk("x", "x")]} ordered={["x"]} gestations={new Map()} onPick={() => {}} onCancel={() => {}} />);
    expect(container.querySelector('[data-testid="gestating"]')).toBeNull();
    expect(container.querySelector(".bone-ph")).toBeTruthy();
  });
});
