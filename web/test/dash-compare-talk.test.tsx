import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Dash from "../src/dash/Dash";
import type { Compare } from "../src/dash/api";
import { setLang } from "../src/dash/i18n";
import { olive, hyena, buffalo } from "./dash-fixtures";

const json = (b: unknown) => new Response(JSON.stringify(b));
const H = (n: number) => ({ n, at: n, analysed: true, noted: n < 3 });
const LONG = "刪".repeat(450);
const CMP: Compare = {
  new: 3, old: 2, mode: "notes", olds: [{ n: 2, noted: true }, { n: 1, noted: true }], same: false, text: "海水很藍。",
  runs: [{ op: "del", id: "d0", at: 0, text: "浪很大。", chars: 4, pinned: true },
    { op: "del", id: "d1", at: 5, text: LONG, chars: 450, pinned: true }],
  hunks: [{ ids: ["d0"], at: 0 }, { ids: ["d1"], at: 5 }], notes_version: 2,
  points: [
    { i: 0, kind: "moved", title: "浪", body: null, question: null, fate: "changed", label: "mixed", quotes: [
      { quote: "浪很大", fate: "gone", old: { start: 0, end: 3 }, new: null, new_text: null, del: "d0" },
      { quote: "很藍", fate: "kept", old: { start: 4, end: 6 }, new: { start: 2, end: 4 }, new_text: null, del: null },
      { quote: "海水藍", fate: "changed", old: { start: 7, end: 10 }, new: { start: 0, end: 4 }, new_text: "海水很藍", del: null },
      { quote: "不見了", fate: "lost", old: null, new: null, new_text: null, del: null }] }],
};
let bodies: Record<string, unknown>[] = [];
let shown = 3;
beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  Element.prototype.scrollIntoView = vi.fn();
  localStorage.clear(); setLang("zh-Hant"); bodies = []; shown = 3;
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function mount(path: string) {
  vi.stubGlobal("fetch", vi.fn(async (u: string, init?: RequestInit) => {
    const p = u.split("?")[0];
    if (p === "/api/themes") return json({ themes: [olive], default: "olive" });
    if (p === "/api/characters") return json({ characters: [hyena, buffalo], default: "hyena" });
    if (p === "/api/works") return json({ works: [{ slug: "d1", title: "海", version: 3, chars: 4, updated_at: 1, state: "ready" }] });
    if (p === "/api/works/d1/compare") return json({ ...CMP, new: shown, old: shown - 1 });
    if (p === "/api/works/d1") return json({ slug: "d1", title: "海", version: shown, versions: [1, 2, 3], text: "海水很藍。", state: "ready", job_id: null, notes_ready: false, history: [H(1), H(2), H(3)] });
    if (p === "/api/works/d1/map") return json({ version: shown, analysis_version: shown, notes_version: shown, beats: [], motifs: [], notes: null });
    if (p.startsWith("/api/discuss/")) { bodies.push(JSON.parse(String(init?.body))); return new Response("", { status: 500 }); }
    return json({ sessions: [], works: [] });
  }));
  render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/w/:slug" element={<Dash />} /></Routes></MemoryRouter>);
}
const say = async (s: string) => {
  fireEvent.click(screen.getByRole("tab", { name: "對話" }));
  fireEvent.change(await screen.findByLabelText("對話輸入"), { target: { value: s } });
  fireEvent.click(screen.getByRole("button", { name: "送出" }));
  await waitFor(() => expect(bodies.length).toBeGreaterThan(0));
};
const paperBring = () => waitFor(() => {
  const b = document.querySelector<HTMLButtonElement>(".paper-bring button");
  expect(b).toBeTruthy();
  return b!;
});
const select = (el: Node, from = 0, to?: number) => {
  const range = document.createRange();
  const text = el.firstChild!;
  range.setStart(text, from); range.setEnd(text, to ?? text.textContent!.length);
  document.getSelection()!.removeAllRanges(); document.getSelection()!.addRange(range);
  act(() => { document.dispatchEvent(new Event("selectionchange")); });
};

describe("對照時的對話", () => {
  it("對照最新版:送出帶 cmp = 對照回應的 old", async () => {
    mount("/w/d1?cmp");
    await screen.findByRole("tab", { name: "去向" });
    await say("改得怎樣");
    expect(bodies[0]).toMatchObject({ cmp: 2, message: "改得怎樣" });
  });

  it("沒開對照:不送 cmp", async () => {
    mount("/w/d1");
    await screen.findByText("海水很藍。");
    await say("嗨");
    expect(bodies[0]).not.toHaveProperty("cmp");
  });

  it("畫面不是最新版:對照開著也不送 cmp,舊字的引用至對話入口都不出現", async () => {
    shown = 2;
    mount("/w/d1?v=2&cmp");
    await screen.findByRole("tab", { name: "去向" });
    await screen.findAllByText("「浪很大」");
    expect(screen.queryAllByRole("button", { name: /^引用至對話/ })).toHaveLength(0);
    const del = await waitFor(() => { const d = document.querySelector("del.cmp-del"); expect(d).toBeTruthy(); return d!; });
    select(del, 0, 2);
    expect(document.querySelector(".paper-bring")).toBeNull();
    await say("嗨");
    expect(bodies[0]).not.toHaveProperty("cmp");
  });

  it("去向卡:點改過/刪掉的舊字本身就引用至對話,還在與找不到的不行;引用後切到對話分頁", async () => {
    mount("/w/d1?cmp");
    await screen.findByRole("tab", { name: "去向" });
    const bring = await screen.findAllByRole("button", { name: /^引用至對話/ });
    expect(bring).toHaveLength(2);
    fireEvent.click(bring[0]);
    expect(screen.getByRole("tab", { name: "對話" }).getAttribute("aria-selected")).toBe("true");
    await say("這句呢");
    expect(bodies[0]).toMatchObject({ quotes: ["浪很大"], cmp: 2 });
  });

  it("稿上:選取跨刪字與新字不出現引用至對話", async () => {
    mount("/w/d1?cmp");
    const del = await waitFor(() => { const d = document.querySelector("del.cmp-del"); expect(d).toBeTruthy(); return d!; });
    const after = del.nextSibling ?? del.parentElement!.nextSibling!;
    const range = document.createRange();
    range.setStart(del.firstChild!, 1); range.setEndAfter(after);
    document.getSelection()!.removeAllRanges(); document.getSelection()!.addRange(range);
    act(() => { document.dispatchEvent(new Event("selectionchange")); });
    expect(document.querySelector(".paper-bring")).toBeNull();
  });

  it("稿上:選取全在一段刪字內才出現引用至對話,太長只帶前 400 字", async () => {
    mount("/w/d1?cmp");
    const dels = await waitFor(() => {
      const d = document.querySelectorAll("del.cmp-del");
      expect(d.length).toBeGreaterThan(0);
      return d;
    });
    select(dels[0], 0, 2);
    fireEvent.click(await paperBring());
    const long = [...document.querySelectorAll("del.cmp-del")].find(d => d.textContent!.length > 400)!;
    select(long);
    fireEvent.click(await paperBring());
    await say("刪掉的");
    const quotes = bodies[0].quotes as string[];
    expect(quotes[0]).toBe("浪很");
    expect(quotes[1]).toBe("刪".repeat(400));
  });
});
