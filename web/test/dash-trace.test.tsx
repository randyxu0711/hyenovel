import { describe, it, expect, vi, beforeEach } from "vitest";
import { useEffect } from "react";
import { render, screen, fireEvent, within } from "@testing-library/react";
import TraceTab from "../src/dash/TraceTab";
import type { Compare, TracePoint, TraceQuote } from "../src/dash/api";
import { setLang } from "../src/dash/i18n";
import { LinksProvider, useLinks, type Links } from "../src/dash/links";

const Q = (quote: string, fate: TraceQuote["fate"], o: Partial<TraceQuote> = {}): TraceQuote => ({
  quote, fate, old: fate === "lost" ? null : { start: 0, end: 1 },
  new: fate === "kept" || fate === "changed" ? { start: 3, end: 6 } : null,
  new_text: fate === "changed" ? "新寫法" : null, del: fate === "gone" || fate === "changed" ? "d0" : null, ...o,
});
const P = (i: number, kind: string, title: string, fate: TracePoint["fate"], label: TracePoint["label"], quotes: TraceQuote[]): TracePoint =>
  ({ i, kind, title, body: `${title}的說明`, question: null, fate, label, quotes });
const CMP = (points: TracePoint[], over: Partial<Compare> = {}): Compare => ({
  new: 3, old: 2, mode: "notes", olds: [{ n: 2, noted: true }], same: false, text: "", runs: [], hunks: [],
  notes_version: 2, points, ...over,
});
const POINTS = [
  P(0, "confused", "卡住的那點", "changed", "changed", [Q("舊句", "changed")]),
  P(1, "wondering", "想問的那點", "changed", "mixed", [Q("還在句", "kept"), Q("刪掉句", "gone", { del: "d1" })]),
  P(2, "moved", "打動的那點", "changed", "gone", [Q("被刪句", "gone")]),
  P(3, "opinion", "沒動的那點", "kept", "kept", [Q("在", "kept")]),
  P(4, "confused", "對不到的那點", "untracked", null, [Q("找不到", "lost")]),
];

let links: Links;
function Probe() { const l = useLinks(); useEffect(() => { links = l; }); return null; }
const mount = (c: Compare) => {
  const runs = vi.fn();
  function RunSpy() { const { registerRun } = useLinks(); useEffect(() => registerRun(runs), [registerRun]); return null; }
  render(<LinksProvider><Probe /><RunSpy /><TraceTab cmp={c} /></LinksProvider>);
  return runs;
};
beforeEach(() => setLang("zh-Hant"));

describe("TraceTab", () => {
  it("groups changed / kept / lost with counts; moved first", () => {
    mount(CMP(POINTS));
    const heads = [...document.querySelectorAll(".trace-group-h")].map(h => h.textContent);
    expect(heads).toEqual(["有動3", "還在1", "對不到1"]);
    const first = document.querySelector(".trace-card")!;
    expect(first.textContent).toContain("打動的那點");
    expect(first.classList.contains("is-raised")).toBe(true);
    expect(document.querySelectorAll(".trace-card.is-raised").length).toBe(1);
  });

  it("kept and lost groups start collapsed and expand", () => {
    mount(CMP(POINTS));
    expect(screen.queryByText("沒動的那點")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /^還在\s*\d/ }));
    expect(screen.getByText("沒動的那點")).toBeTruthy();
  });

  it("same opens kept group by default", () => {
    mount(CMP([POINTS[3]], { same: true }));
    expect(screen.getByText("沒動的那點")).toBeTruthy();
  });

  it("card head shows label; mixed lists per-quote state, single does not", () => {
    mount(CMP(POINTS));
    const mixed = screen.getByText("想問的那點").closest(".trace-card") as HTMLElement;
    expect(within(mixed).getByText("有動", { selector: ".trace-state" })).toBeTruthy();
    expect(within(mixed).getAllByText(/^(還在|刪掉)$/, { selector: ".trace-qstate" }).length).toBe(2);
    const moved = screen.getByText("打動的那點").closest(".trace-card") as HTMLElement;
    expect(within(moved).getByText("刪掉", { selector: ".trace-state" })).toBeTruthy();
    expect(moved.querySelector(".trace-qstate")).toBeNull();
  });

  it("gone quote jumps to its del run", () => {
    const runs = mount(CMP(POINTS));
    fireEvent.click(screen.getByRole("button", { name: "被刪句" }));
    expect(runs).toHaveBeenCalledWith("d0");
  });

  it("changed quote shows struck old text and new text", () => {
    mount(CMP(POINTS));
    const card = screen.getByText("卡住的那點").closest(".trace-card") as HTMLElement;
    expect(card.querySelector("del")?.textContent).toContain("舊句");
    expect(card.textContent).toContain("新寫法");
  });

  it("body hidden until title clicked", () => {
    mount(CMP(POINTS));
    expect(screen.queryByText("卡住的那點的說明")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "卡住的那點" }));
    expect(screen.getByText("卡住的那點的說明")).toBeTruthy();
  });

  it("hover and click set trace point", () => {
    mount(CMP(POINTS));
    const card = screen.getByText("打動的那點").closest(".trace-card") as HTMLElement;
    fireEvent.mouseEnter(card);
    expect(links.trace.hover).toBe(2);
    fireEvent.mouseLeave(card);
    expect(links.trace.hover).toBeNull();
    fireEvent.click(card);
    expect(links.trace.picked).toBe(2);
  });

  it("no judgement words", () => {
    mount(CMP(POINTS));
    expect(document.body.textContent).not.toMatch(/可能|錯|!|!/);
  });
});
