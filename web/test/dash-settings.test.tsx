import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Dash from "../src/dash/Dash";
import Paper from "../src/dash/Paper";
import { setLang } from "../src/dash/i18n";
import { getThemeState, setMode } from "../src/dash/theme";
import { LinksProvider } from "../src/dash/links";
import { CharactersProvider, makeCharacters } from "../src/dash/useCharacters";
import { olive, grass, hyena, buffalo, deer } from "./dash-fixtures";

afterEach(() => vi.unstubAllGlobals());
beforeEach(() => { vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null); localStorage.clear(); setMode("system"); });
const json = (b: unknown) => new Response(JSON.stringify(b));

const row = (session: string, legacy: boolean) => ({
  session, slug: "d1", title: "舊的", started_at: 1, last_at: 2, turns: 2, character: null, mode: null,
  preview: `預覽${session}`, legacy,
});
const DETAIL = {
  session: "old1", slug: "d1", title: "舊的", legacy: true, version: 1,
  turns: [
    { role: "user", text: "我問的那句", ts: 1, mode: null, character: null, quotes: [], spans: [] },
    { role: "assistant", text: "舊討論的回答", ts: 2, mode: "direct", character: "buffalo", quotes: [], spans: [] },
  ],
};

function mount(path = "/settings") {
  setLang("zh-Hant");
  const f = vi.fn(async (u: string) => {
    if (u === "/api/themes") return json({ themes: [olive, grass], default: "olive" });
    if (u === "/api/characters") return json({ characters: [hyena, buffalo, deer], default: "hyena" });
    if (u === "/api/works") return json({ works: [{ slug: "d1", title: "舊的", version: 1, chars: 4, updated_at: 1, state: "ready" }] });
    if (u.startsWith("/api/sessions/old1")) return json(DETAIL);
    if (u.startsWith("/api/sessions")) return json({ sessions: [row("old1", true), row("new1", false), row("old2", true)] });
    return json({ sessions: [] });
  });
  vi.stubGlobal("fetch", f);
  render(<MemoryRouter initialEntries={[path]}>
    <Routes><Route path="/" element={<Dash />} /><Route path="/settings" element={<Dash />} /></Routes>
  </MemoryRouter>);
  return f;
}
const page = async () => within(await screen.findByRole("region", { name: "設定" }));

describe("設定頁", () => {
  it("晝夜三選一改 pref,並跟左欄的一鍵晝夜同步", async () => {
    mount();
    const p = await page();
    fireEvent.click(p.getByRole("button", { name: "夜" }));
    expect(getThemeState().pref).toBe("dark");
    expect(localStorage.getItem("hyenovel.mode")).toBe("dark");
    expect(p.getByRole("button", { name: "夜" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "切換晝夜" }));   // 左欄:夜 → 晝
    expect(getThemeState().pref).toBe("light");
    expect(p.getByRole("button", { name: "晝" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(p.getByRole("button", { name: "跟系統" }));
    expect(getThemeState().pref).toBe("system");
  });

  it("色票數 = /api/themes 數,點了換主題", async () => {
    mount();
    const p = await page();
    const sw = p.getAllByRole("button", { name: /暖橄欖|草原灰夜/ });
    expect(sw).toHaveLength(2);
    fireEvent.click(p.getByRole("button", { name: "草原灰夜" }));
    expect(getThemeState().theme?.id).toBe("grass");
    expect(localStorage.getItem("hyenovel.theme")).toBe("grass");
    expect(p.getByRole("button", { name: "草原灰夜" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("語言切換後標題變英文", async () => {
    mount();
    const p = await page();
    fireEvent.click(p.getByRole("button", { name: "English" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Settings" })).toBeTruthy();
    expect(localStorage.getItem("hyenovel.lang")).toBe("en");
  });

  it("稿字級存 localStorage,Paper 套 data-size", async () => {
    mount();
    const p = await page();
    fireEvent.click(p.getByRole("button", { name: "大" }));
    expect(localStorage.getItem("hyenovel.paperSize")).toBe("l");
    const { container } = render(
      <CharactersProvider value={makeCharacters([hyena], "hyena")}><LinksProvider>
        <Paper text="一行" title="x" marks={[]} onBring={() => {}} />
      </LinksProvider></CharactersProvider>);
    expect(container.querySelector(".paper-sheet")?.getAttribute("data-size")).toBe("l");
    fireEvent.click(p.getByRole("button", { name: "小" }));
    expect(localStorage.getItem("hyenovel.paperSize")).toBe("s");
  });

  it("陪讀者:每位有名字與 line;選水牛為預設,進門輸入框是水牛", async () => {
    mount();
    const p = await page();
    expect(p.getAllByText("一句話")).toHaveLength(3);
    fireEvent.click(p.getByRole("radio", { name: /水牛/ }));
    expect(localStorage.getItem("hyenovel.companion")).toBe("buffalo");
    expect((p.getByRole("radio", { name: /水牛/ }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "新對話" }));
    expect(await screen.findByRole("button", { name: "陪讀者" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "陪讀者" }).textContent).toContain("水牛");
  });

  it("「預設」只標在選中的那位", async () => {
    mount();
    const p = await page();
    const tagged = () => p.getAllByRole("radio").filter(r => r.closest("label")!.textContent!.includes("預設"));
    expect(tagged()).toHaveLength(1);
    expect((tagged()[0] as HTMLInputElement).checked).toBe(true);
    fireEvent.click(p.getByRole("radio", { name: /鹿/ }));
    expect(tagged()).toEqual([p.getByRole("radio", { name: /鹿/ })]);
  });

  it("舊討論:只數 legacy 局,打開封存看得到逐字,沒有輸入框", async () => {
    const f = mount();
    const p = await page();
    expect(f.mock.calls.some(c => String(c[0]) === "/api/sessions?limit=100&legacy=1")).toBe(true);
    await waitFor(() => expect(p.getByText(/2/)).toBeTruthy());
    fireEvent.click(p.getByRole("button", { name: "打開封存" }));
    expect(p.getByText("預覽old1")).toBeTruthy();
    expect(p.getByText("預覽old2")).toBeTruthy();
    expect(p.queryByText("預覽new1")).toBeNull();
    fireEvent.click(p.getByRole("button", { name: /預覽old1/ }));
    expect(await p.findByText("舊討論的回答")).toBeTruthy();
    expect(p.getByText("我問的那句")).toBeTruthy();
    expect(p.queryByRole("textbox")).toBeNull();
    fireEvent.click(p.getByRole("button", { name: "回清單" }));
    expect(p.getByText("預覽old2")).toBeTruthy();
  });

  it("沒有死控制項:每個沒被選中的 button/radio 點了都改變狀態;不出現未實作項目", async () => {
    mount();
    const p = await page();
    await waitFor(() => expect(p.getByText(/2/)).toBeTruthy());
    const snap = () => JSON.stringify(Object.entries(localStorage)) + document.querySelector(".dash-settings")!.innerHTML;
    const controls = () => [...document.querySelectorAll<HTMLElement>(".dash-settings button, .dash-settings input")];
    expect(controls().length).toBeGreaterThan(10);
    for (let i = 0; i < controls().length; i++) {
      const el = controls()[i];
      if (el.getAttribute("aria-pressed") === "true" || (el as HTMLInputElement).checked) continue;
      const before = snap();
      fireEvent.click(el);
      await waitFor(() => expect(snap()).not.toBe(before));
    }
    const text = document.querySelector(".dash-settings")!.textContent!;
    for (const w of ["主動先開口", "用量", "資料庫"]) expect(text).not.toContain(w);
  });
});
