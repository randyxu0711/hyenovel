import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import Dash from "../src/dash/Dash";
import { setLang } from "../src/dash/i18n";
import { olive, hyena, buffalo } from "./dash-fixtures";

const json = (b: unknown) => new Response(JSON.stringify(b));
const WORKS = [
  { slug: "d1", title: "海", version: 1, chars: 4, updated_at: 2, state: "ready" },
  { slug: "d2", title: "潮汐", version: 1, chars: 4, updated_at: 1, state: "ready" },
];
beforeEach(() => { vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null); localStorage.clear(); setLang("zh-Hant"); });
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function Where() { const l = useLocation(); return <output data-testid="loc">{l.pathname}</output>; }
function mount(path: string) {
  vi.stubGlobal("fetch", vi.fn(async (u: string) => {
    const p = u.split("?")[0];
    if (p === "/api/themes") return json({ themes: [olive], default: "olive" });
    if (p === "/api/characters") return json({ characters: [hyena, buffalo], default: "hyena" });
    if (p === "/api/works") return json({ works: WORKS });
    if (p.endsWith("/map")) return json({ version: 1, analysis_version: null, notes_version: null, beats: [], motifs: [], notes: null });
    if (p.startsWith("/api/works/") && !p.endsWith("/sessions")) return json({ slug: "d1", title: "海", version: 1, versions: [1], text: "內文一行", state: "ready", job_id: null, notes_ready: false });
    return json({ sessions: [] });
  }));
  render(<MemoryRouter initialEntries={[path]}><Where />
    <Routes><Route path="/" element={<Dash />} /><Route path="/w/:slug" element={<Dash />} /><Route path="/settings" element={<Dash />} /></Routes>
  </MemoryRouter>);
}
const ctrlK = (el: Element | Document = document) => fireEvent.keyDown(el, { key: "k", ctrlKey: true });
const where = () => screen.getByTestId("loc").textContent;

describe("鍵盤", () => {
  it("/ 在作品頁聚焦對話輸入框;在 textarea 內打 / 不被攔", async () => {
    mount("/w/d1");
    const box = await screen.findByLabelText("對話輸入");
    expect(fireEvent.keyDown(document.body, { key: "/" })).toBe(false);   // preventDefault 了
    expect(document.activeElement).toBe(box);
    expect(fireEvent.keyDown(box, { key: "/" })).toBe(true);              // 沒攔
  });
  it("/ 在進門頁聚焦進門輸入框", async () => {
    mount("/");
    await screen.findByRole("navigation");
    await waitFor(() => expect(document.querySelector(".home textarea")).toBeTruthy());
    fireEvent.keyDown(document.body, { key: "/" });
    expect(document.activeElement).toBe(document.querySelector(".home textarea"));
  });
  it("Ctrl+K 開指令框(焦點在輸入框裡也開);輸入「潮」只剩含「潮」的;Enter 導到作品", async () => {
    mount("/w/d1");
    const box = await screen.findByLabelText("對話輸入");
    ctrlK(box);
    const dlg = await screen.findByRole("dialog", { name: "指令框" });
    const input = within(dlg).getByRole("combobox");
    expect(document.activeElement).toBe(input);
    fireEvent.change(input, { target: { value: "潮" } });
    const opts = within(dlg).getAllByRole("option");
    expect(opts.map(o => o.textContent)).toEqual(["作品:潮汐"]);
    expect(input.getAttribute("aria-activedescendant")).toBe(opts[0].id);
    fireEvent.keyDown(input, { key: "Enter" });
    expect(where()).toBe("/w/d2");
    expect(screen.queryByRole("dialog", { name: "指令框" })).toBeNull();
  });
  it("⌘K 也開;方向鍵移動選取;Esc 關閉並把焦點還給原本的元素", async () => {
    mount("/w/d1");
    const box = await screen.findByLabelText("對話輸入");
    box.focus();
    fireEvent.keyDown(document, { key: "k", metaKey: true });
    const dlg = await screen.findByRole("dialog", { name: "指令框" });
    const input = within(dlg).getByRole("combobox");
    const sel = () => within(dlg).getAllByRole("option").findIndex(o => o.getAttribute("aria-selected") === "true");
    expect(sel()).toBe(0);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(sel()).toBe(1);
    fireEvent.keyDown(input, { key: "ArrowUp" });
    fireEvent.keyDown(input, { key: "ArrowUp" });
    expect(sel()).toBe(within(dlg).getAllByRole("option").length - 1);   // 往上繞回最後一項
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "指令框" })).toBeNull();
    expect(document.activeElement).toBe(box);
  });
  it("選「切換晝夜」→ 晝夜換了;選「設定」→ 導到設定;選陪讀者 → 存成預設", async () => {
    mount("/w/d1");
    await screen.findByLabelText("對話輸入");
    const mode = () => document.querySelector(".dash")!.getAttribute("data-mode");
    const before = mode();
    ctrlK();
    fireEvent.change(await screen.findByRole("combobox"), { target: { value: "切換晝夜" } });
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Enter" });
    await waitFor(() => expect(mode()).not.toBe(before));
    ctrlK();
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("option", { name: "陪讀者:水牛" }));
    expect(localStorage.getItem("hyenovel.companion")).toBe("buffalo");
    ctrlK();
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("option", { name: "設定" }));
    expect(where()).toBe("/settings");
  });
  it("找不到時說沒有符合的", async () => {
    mount("/w/d1");
    await screen.findByLabelText("對話輸入");
    ctrlK();
    fireEvent.change(await screen.findByRole("combobox"), { target: { value: "zzzz" } });
    expect(screen.getByText("沒有符合的")).toBeTruthy();
    expect(screen.queryAllByRole("option")).toHaveLength(0);
  });
  it("Esc 關掉作品選單浮層", async () => {
    mount("/w/d1");
    await screen.findByLabelText("對話輸入");
    fireEvent.click(screen.getByRole("button", { name: "作品" }));
    expect(screen.getByRole("dialog", { name: "作品" })).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "作品" })).toBeNull();
  });
  it("輸入法組字中:Enter / 方向鍵 / Esc 不執行、不移動、不關閉(isComposing 與 keyCode 229)", async () => {
    mount("/w/d1");
    await screen.findByLabelText("對話輸入");
    ctrlK();
    const dlg = await screen.findByRole("dialog", { name: "指令框" });
    const input = within(dlg).getByRole("combobox");
    const sel = () => within(dlg).getAllByRole("option").findIndex(o => o.getAttribute("aria-selected") === "true");
    for (const init of [{ isComposing: true }, { keyCode: 229 }]) {
      fireEvent.keyDown(input, { key: "ArrowDown", ...init });
      expect(sel()).toBe(0);
      fireEvent.keyDown(input, { key: "Enter", ...init });
      expect(where()).toBe("/w/d1");
      fireEvent.keyDown(input, { key: "Escape", ...init });
      expect(screen.getByRole("dialog", { name: "指令框" })).toBeTruthy();
    }
  });
  it("組字中的 / 不聚焦輸入框", async () => {
    mount("/w/d1");
    const box = await screen.findByLabelText("對話輸入");
    fireEvent.keyDown(document.body, { key: "/", isComposing: true });
    expect(document.activeElement).not.toBe(box);
    fireEvent.keyDown(document.body, { key: "/", keyCode: 229 });
    expect(document.activeElement).not.toBe(box);
  });
});
