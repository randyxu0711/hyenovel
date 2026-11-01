import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Dash from "../src/dash/Dash";
import { setLang } from "../src/dash/i18n";
import { marksFrom } from "../src/dash/Side";
import { makeCharacters } from "../src/dash/useCharacters";
import { olive, hyena, buffalo, deer } from "./dash-fixtures";

const json = (b: unknown) => new Response(JSON.stringify(b));
function mount() {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const p = url.split("?")[0];
    if (p === "/api/themes") return json({ themes: [olive], default: "olive" });
    if (p === "/api/characters") return json({ characters: [hyena, buffalo, deer], default: "hyena" });
    if (p === "/api/works") return json({ works: [{ slug: "d1", title: "海", version: 1, chars: 4, updated_at: 1, state: "ready" }] });
    if (p === "/api/works/d1") return json({ slug: "d1", title: "海", version: 1, versions: [1], text: "內文一行", state: "ready", job_id: null, notes_ready: false });
    if (p === "/api/works/d1/map") return json({ version: 1, analysis_version: 1, notes_version: null, notes: null, motifs: [],
      beats: [{ id: "b1", label: "開頭", intensity: 0.5, span: { quote: "內文", start: 0, end: 2 } }] });
    return json({ sessions: [] });
  }));
  return render(<MemoryRouter initialEntries={["/w/d1"]}><Routes><Route path="/w/:slug" element={<Dash />} /></Routes></MemoryRouter>);
}
const tab = (name: string) => screen.getByRole("tab", { name });

beforeEach(() => { setLang("zh-Hant"); localStorage.clear(); });
afterEach(() => vi.unstubAllGlobals());

describe("右欄分頁", () => {
  it("三個分頁;切到筆記、結構圖時稿仍在", async () => {
    const { container } = mount();
    await screen.findByText("內文一行");
    expect(tab("對話").getAttribute("aria-selected")).toBe("true");
    fireEvent.click(tab("筆記"));
    expect(tab("筆記").getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("內文一行")).toBeTruthy();
    expect(await screen.findByText("這篇是舊版流程讀的,沒有筆記。")).toBeTruthy();
    fireEvent.click(tab("結構圖"));
    expect(screen.getByText("內文一行")).toBeTruthy();
    expect(container.querySelectorAll("button.dash-mcol")).toHaveLength(1);
  });
  it("切走對話時對話仍掛著(草稿不丟)", async () => {
    mount();
    fireEvent.change(await screen.findByLabelText("對話輸入"), { target: { value: "還沒寫完" } });
    fireEvent.click(tab("結構圖"));
    fireEvent.click(tab("對話"));
    expect((screen.getByLabelText("對話輸入") as HTMLTextAreaElement).value).toBe("還沒寫完");
  });
});

describe("分隔線", () => {
  it("可用鍵盤拖;寬度存 hyenovel.split,右欄最少 380、稿最少 380(收起的左欄 56 不算)", async () => {
    const { unmount } = mount();
    const grip = await screen.findByRole("separator", { name: "拖曳調整寬度" });
    fireEvent.keyDown(grip, { key: "ArrowLeft" });
    const w = Number(localStorage.getItem("hyenovel.split"));
    expect(w).toBeGreaterThanOrEqual(380);
    for (let i = 0; i < 60; i++) fireEvent.keyDown(grip, { key: "ArrowLeft" });
    // jsdom 寬 1024:右欄最多 1024 - 56 - 分隔線 - 380
    expect(Number(localStorage.getItem("hyenovel.split"))).toBeLessThanOrEqual(1024 - 56 - 380);
    for (let i = 0; i < 60; i++) fireEvent.keyDown(grip, { key: "ArrowRight" });
    expect(Number(localStorage.getItem("hyenovel.split"))).toBe(380);
    unmount();
    localStorage.setItem("hyenovel.split", "450");
    mount();
    await screen.findByText("內文一行");
    expect((document.querySelector(".dash") as HTMLElement).style.getPropertyValue("--dash-split")).toBe("450px");
  });
});

describe("marksFrom", () => {
  const chars = makeCharacters([hyena, buffalo, deer], "hyena");
  const turn = (role: string, spans: { quote: string; start: number | null; end: number | null }[], character: string | null = null, mode: string | null = null) =>
    ({ role, text: "", ts: 0, mode, character, quotes: [], spans });
  it("assistant 的 spans(有位置的)→ 該 turn 角色的痕跡;user 的引文不畫", () => {
    const marks = marksFrom([
      turn("user", [{ quote: "u", start: 0, end: 1 }]),
      turn("assistant", [{ quote: "a", start: 2, end: 4 }, { quote: "x", start: null, end: null }], "buffalo"),
      turn("assistant", [{ quote: "b", start: 5, end: 6 }], null, "imaginative"),
    ], chars);
    expect(marks.map(m => [m.start, m.end, m.character])).toEqual([[2, 4, "buffalo"], [5, 6, "deer"]]);
    expect(new Set(marks.map(m => m.id)).size).toBe(2);
  });
  it("同一位置多筆取最後一筆", () => {
    const marks = marksFrom([
      turn("assistant", [{ quote: "a", start: 2, end: 4 }], "buffalo"),
      turn("assistant", [{ quote: "a", start: 2, end: 4 }], "hyena"),
    ], chars);
    expect(marks.map(m => m.character)).toEqual(["hyena"]);
  });
});
