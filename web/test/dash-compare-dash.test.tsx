import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import Dash from "../src/dash/Dash";
import type { Compare } from "../src/dash/api";
import { setLang } from "../src/dash/i18n";
import { olive, hyena, buffalo } from "./dash-fixtures";

const json = (b: unknown) => new Response(JSON.stringify(b));
const H = (n: number) => ({ n, at: n, analysed: true, noted: n < 2 });
const CMP: Compare = {
  new: 2, old: 1, mode: "notes", olds: [{ n: 1, noted: true }], same: false, text: "海水很藍。",
  runs: [{ op: "ins", id: "i0", start: 0, end: 2 }], hunks: [{ ids: ["i0"], at: 0 }], notes_version: 1,
  points: [{ i: 0, kind: "moved", title: "藍", body: null, question: null, fate: "kept", label: "kept",
    quotes: [{ quote: "很藍", fate: "kept", old: { start: 0, end: 2 }, new: { start: 2, end: 4 }, new_text: null, del: null }] }],
};
const narrow = (on: boolean) => {
  window.matchMedia = ((q: string) => ({ matches: on && q === "(max-width:1100px)", media: q, addEventListener() {}, removeEventListener() {} })) as unknown as typeof window.matchMedia;
};
beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  Element.prototype.scrollIntoView = vi.fn();
  localStorage.clear(); setLang("zh-Hant");
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); delete (window as { matchMedia?: unknown }).matchMedia; });

function Where() { const l = useLocation(); return <output data-testid="loc">{l.search}</output>; }
function mount(path = "/w/d1") {
  vi.stubGlobal("fetch", vi.fn(async (u: string) => {
    const p = u.split("?")[0];
    if (p === "/api/themes") return json({ themes: [olive], default: "olive" });
    if (p === "/api/characters") return json({ characters: [hyena, buffalo], default: "hyena" });
    if (p === "/api/works") return json({ works: [{ slug: "d1", title: "海", version: 2, chars: 4, updated_at: 1, state: "ready" }] });
    if (p === "/api/works/d1/compare") return json(CMP);
    if (p === "/api/works/d1") return json({ slug: "d1", title: "海", version: 2, versions: [1, 2], text: "海水很藍。", state: "ready", job_id: null, notes_ready: false, history: [H(1), H(2)] });
    if (p === "/api/works/d1/map") return json({ version: 2, analysis_version: 2, notes_version: 2, beats: [], motifs: [], notes: null });
    return json({ sessions: [], works: [] });
  }));
  render(<MemoryRouter initialEntries={[path]}><Where />
    <Routes><Route path="/w/:slug" element={<Dash />} /></Routes></MemoryRouter>);
}
const loc = () => screen.getByTestId("loc").textContent;

describe("對照接到 Dash", () => {
  it("右欄換成去向並選中;結構圖停用;離開回到筆記名", async () => {
    mount("/w/d1?cmp");
    const tab = await screen.findByRole("tab", { name: "去向" });
    expect(tab.getAttribute("aria-selected")).toBe("true");
    expect(await screen.findByRole("button", { name: /^還在\s*1/ })).toBeTruthy();
    const chart = screen.getByRole("tab", { name: "結構圖" });
    expect(chart.getAttribute("data-empty")).toBe("true");
    expect((chart as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "結束對照" }));
    await waitFor(() => expect(screen.queryByRole("tab", { name: "去向" })).toBeNull());
    expect(screen.getByRole("tab", { name: "筆記" })).toBeTruthy();
  });

  it("窄螢幕:窗格切換第二格是去向", async () => {
    narrow(true); mount("/w/d1?cmp");
    expect(await screen.findByRole("button", { name: "去向" })).toBeTruthy();
  });

  it("⌘K 對照上一版 → ?cmp", async () => {
    mount("/w/d1");
    await screen.findByText("海水很藍。");
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    fireEvent.click(await screen.findByRole("option", { name: /對照上一版/ }));
    expect(loc()).toBe("?cmp=");
  });

  it("專注+對照:Esc 先離開對照,專注還在", async () => {
    mount("/w/d1?cmp");
    await screen.findByRole("tab", { name: "去向" });
    fireEvent.click(screen.getByRole("button", { name: "只看稿" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(loc()).toBe("");
    expect(document.querySelector(".dash")!.getAttribute("data-focus")).toBe("true");
  });
});
