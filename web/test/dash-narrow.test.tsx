import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Dash from "../src/dash/Dash";
import { setLang } from "../src/dash/i18n";
import { olive, hyena, buffalo } from "./dash-fixtures";

const json = (b: unknown) => new Response(JSON.stringify(b));
const sse = (...evs: [string, unknown][]) => new Response(new ReadableStream({
  start(c) {
    const enc = new TextEncoder();
    for (const [event, data] of evs) c.enqueue(enc.encode(`data: ${JSON.stringify({ event, data })}\n\n`));
    c.close();
  },
}));
const narrow = (on: boolean) => {
  window.matchMedia = ((q: string) => ({ matches: on && q === "(max-width:1100px)", media: q, addEventListener() {}, removeEventListener() {} })) as unknown as typeof window.matchMedia;
};
beforeEach(() => { vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null); localStorage.clear(); setLang("zh-Hant"); });
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); delete (window as { matchMedia?: unknown }).matchMedia; });

function mount() {
  vi.stubGlobal("fetch", vi.fn(async (u: string) => {
    const p = u.split("?")[0];
    if (p === "/api/themes") return json({ themes: [olive], default: "olive" });
    if (p === "/api/characters") return json({ characters: [hyena, buffalo], default: "hyena" });
    if (p === "/api/works") return json({ works: [{ slug: "d1", title: "海", version: 1, chars: 4 }] });
    if (p === "/api/works/d1") return json({ slug: "d1", title: "海", version: 1, versions: [1], text: "海水很藍", state: "ready", job_id: null, notes_ready: false });
    if (p === "/api/works/d1/map") return json({ version: 1, analysis_version: null, notes_version: null, beats: [], motifs: [], notes: null });
    if (p.startsWith("/api/discuss/")) return sse(
      ["message", { role: "assistant", text: "「海」好", session_id: "s1", mode: "slow", character: "hyena", spans: [{ quote: "海", start: 0, end: 1 }] }],
      ["done", { ok: true, session_id: "s1" }]);
    return json({ sessions: [] });
  }));
  render(<MemoryRouter initialEntries={["/w/d1"]}><Routes><Route path="/w/:slug" element={<Dash />} /></Routes></MemoryRouter>);
}
const paper = () => document.querySelector(".dash-desk") as HTMLElement;
const side = () => document.querySelector(".dash-side") as HTMLElement;

describe("窄螢幕單窗格", () => {
  it("只見稿;兩個窗格都還掛著,只藏另一邊;按「對話」只見右欄", async () => {
    narrow(true); mount();
    await screen.findByText("海水很藍");
    await waitFor(() => expect(side().hidden).toBe(true));
    expect(paper().hidden).toBe(false);
    expect(screen.queryByRole("separator")).toBeNull();
    expect(side().querySelector("textarea")).toBeTruthy();   // 仍在 DOM,jump 才找得到
    fireEvent.click(screen.getByRole("button", { name: "對話" }));
    expect(paper().hidden).toBe(true);
    expect(side().hidden).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "稿" }));
    expect(side().hidden).toBe(true);
  });
  it("寬螢幕:兩邊都見、沒有「稿|對話」切換", async () => {
    narrow(false); mount();
    await screen.findByText("海水很藍");
    expect(paper().hidden).toBe(false);
    expect(side().hidden).toBe(false);
    expect(screen.queryByRole("group", { name: "切換窗格" })).toBeNull();
    expect(screen.getByRole("separator")).toBeTruthy();
  });
  it("點引文 → 切回稿", async () => {
    narrow(true); mount();
    await screen.findByText("海水很藍");
    fireEvent.click(screen.getByRole("button", { name: "對話" }));
    fireEvent.change(screen.getByLabelText("對話輸入"), { target: { value: "嗨" } });
    fireEvent.click(screen.getByRole("button", { name: "送出" }));
    fireEvent.click(await screen.findByRole("button", { name: "「海」" }));
    expect(paper().hidden).toBe(false);
    expect(side().hidden).toBe(true);
  });
});
