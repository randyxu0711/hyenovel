import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import Dash from "../src/dash/Dash";
import Paper from "../src/dash/Paper";
import { loadPaperFlow, setPaperFlow } from "../src/dash/paperFlow";
import { blobPath } from "../src/dash/Blob";
import { setLang } from "../src/dash/i18n";
import { getThemeState, setMode } from "../src/dash/theme";
import { LinksProvider } from "../src/dash/links";
import { CharactersProvider, makeCharacters } from "../src/dash/useCharacters";
import { olive, grass, hyena, buffalo, deer } from "./dash-fixtures";

afterEach(() => vi.unstubAllGlobals());
beforeEach(() => { vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null); localStorage.clear(); setMode("system"); });
const json = (b: unknown) => new Response(JSON.stringify(b));
function Where() { return <output data-testid="loc">{useLocation().pathname}</output>; }

const row = (session: string, legacy: boolean) => ({
  session, slug: "d1", title: "舊的", started_at: 1, last_at: 2, turns: 2, character: null, mode: null,
  preview: `預覽${session}`, legacy,
});
const DETAIL = {
  session: "old1", slug: "d1", title: "舊的", legacy: true, version: 1,
  turns: [
    { role: "user", text: "我問的那句", ts: 1, mode: null, character: null, quotes: [], spans: [] },
    { role: "assistant", text: "舊討論的回答", ts: 2, mode: "direct", character: "buffalo", quotes: [], spans: [] },
    { role: "user", text: "再問", ts: 3, mode: null, character: null, quotes: [], spans: [] },
    { role: "assistant", text: "同一位再答", ts: 4, mode: "direct", character: "buffalo", quotes: [], spans: [] },
  ],
};

function mount(path = "/settings") {
  setLang("zh-Hant");
  const f = vi.fn(async (u: string) => {
    if (u === "/api/themes") return json({ themes: [olive, grass], default: "olive" });
    if (u === "/api/characters") return json({ characters: [hyena, buffalo, deer], default: "hyena" });
    if (u === "/api/works") return json({ works: [{ slug: "d1", title: "舊的", version: 1, chars: 4, updated_at: 1, state: "ready" }] });
    if (u === "/api/works/d1") return json({ slug: "d1", title: "舊的", version: 1, versions: [1], text: "內文", state: "ready", job_id: null, notes_ready: false });
    if (u === "/api/memory") return json({ memories: [], caps: { author: 800, work: 600 } });
    if (u.startsWith("/api/sessions/old1")) return json(DETAIL);
    if (u.startsWith("/api/sessions")) return json({ sessions: [row("old1", true), row("new1", false), row("old2", true)] });
    return json({ sessions: [] });
  });
  vi.stubGlobal("fetch", f);
  render(<MemoryRouter initialEntries={[path]}><Where />
    <Routes><Route path="/" element={<Dash />} /><Route path="/w/:slug" element={<Dash />} /><Route path="/settings" element={<Dash />} /></Routes>
  </MemoryRouter>);
  return f;
}
const page = async () => within(await screen.findByRole("region", { name: "設定" }));
const shelf = async () => within(await screen.findByRole("navigation"));
const go = async (name: string) => fireEvent.click((await shelf()).getByRole("button", { name }));

describe("設定頁", () => {
  it("在 /settings:書架沒有作品清單與篩選框,有回去鍵與三個分區", async () => {
    mount();
    const nav = await shelf();
    expect(nav.queryByText("舊的")).toBeNull();
    expect(nav.queryByRole("searchbox")).toBeNull();
    const names = within(nav.getByRole("group", { name: "設定分區" })).getAllByRole("button").map(b => b.getAttribute("aria-label"));
    expect(names).toEqual(["回到進門", "外觀", "陪讀者", "記憶", "舊討論"]);
    expect(nav.getByRole("button", { name: "外觀" }).getAttribute("aria-current")).toBe("true");
  });
  it("記憶分區畫出記憶頁,圖示是記憶專用的", async () => {
    mount();
    const nav = await shelf();
    const key = nav.getByRole("button", { name: "記憶" });
    fireEvent.click(key);
    expect(await screen.findByRole("textbox", { name: "新增記憶" })).toBeTruthy();
    expect(key.getAttribute("aria-current")).toBe("true");
    expect(document.querySelector(".dash-settings")!.getAttribute("data-section")).toBe("memory");
  });
  it("沒開過作品 → 「回到進門」到 /;開過〈舊的〉→「回到〈舊的〉」到 /w/d1", async () => {
    mount();
    await go("回到進門");
    expect(screen.getByTestId("loc").textContent).toBe("/");
    await go("展開書架");
    fireEvent.click((await shelf()).getByRole("button", { name: /^舊的/ }));
    expect(screen.getByTestId("loc").textContent).toBe("/w/d1");
    await go("設定");
    await go("回到〈舊的〉");
    expect(screen.getByTestId("loc").textContent).toBe("/w/d1");
  });
  it("點「陪讀者」→ 內容換成預設陪讀者單選,沒有預覽欄;點「外觀」→ 有預覽欄", async () => {
    mount();
    const p = await page();
    expect(p.getByRole("figure", { name: "預覽" })).toBeTruthy();
    await go("陪讀者");
    expect(p.getAllByRole("radio")).toHaveLength(3);
    expect(p.queryByRole("figure")).toBeNull();
    expect(p.getByRole("heading", { level: 1, name: "陪讀者" })).toBeTruthy();
    await go("外觀");
    expect(p.getByRole("figure", { name: "預覽" })).toBeTruthy();
  });
  it("晝夜是三顆圖示鈕(跟系統/晝/夜),aria-pressed 跟 pref", async () => {
    mount();
    const p = await page();
    const seg = within(p.getByRole("group", { name: "晝夜" }));
    expect(seg.getAllByRole("button").map(b => b.getAttribute("aria-label"))).toEqual(["跟系統", "晝", "夜"]);
    for (const b of seg.getAllByRole("button")) expect(b.querySelector("svg")).toBeTruthy();
    fireEvent.click(seg.getByRole("button", { name: "夜" }));
    expect(getThemeState().pref).toBe("dark");
    expect(localStorage.getItem("hyenovel.mode")).toBe("dark");
    expect(seg.getByRole("button", { name: "夜" }).getAttribute("aria-pressed")).toBe("true");
  });
  it("⌘K 切換晝夜:夜 → 晝;翻回系統那一邊時存成「跟系統」", async () => {
    mount();   // jsdom 沒有 matchMedia:系統 = 晝
    const p = await page();
    const seg = within(p.getByRole("group", { name: "晝夜" }));
    fireEvent.click(seg.getByRole("button", { name: "夜" }));
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    fireEvent.click(await screen.findByRole("option", { name: "切換晝夜" }));
    expect(getThemeState().mode).toBe("light");
    expect(getThemeState().pref).toBe("system");
    expect(seg.getByRole("button", { name: "跟系統" }).getAttribute("aria-pressed")).toBe("true");
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
    expect(await screen.findByRole("heading", { level: 1, name: "Appearance" })).toBeTruthy();
    expect(localStorage.getItem("hyenovel.lang")).toBe("en");
  });

  it("排法:預設直排;按橫排 → 存成 h", async () => {
    mount();
    const p = await page();
    const g = within(p.getByRole("group", { name: "排法" }));
    expect(g.getByRole("button", { name: "直排" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(g.getByRole("button", { name: "橫排" }));
    expect(loadPaperFlow()).toBe("h");
    expect(g.getByRole("button", { name: "橫排" }).getAttribute("aria-pressed")).toBe("true");
    setPaperFlow("v");
  });

  it("稿字級存 localStorage,預覽紙與 Paper 都套 data-size", async () => {
    mount();
    const p = await page();
    const mini = () => p.getByRole("figure", { name: "預覽" }).querySelector("p")!.getAttribute("data-size");
    fireEvent.click(p.getByRole("button", { name: "大" }));
    expect(localStorage.getItem("hyenovel.paperSize")).toBe("l");
    expect(mini()).toBe("l");
    const { container } = render(
      <CharactersProvider value={makeCharacters([hyena], "hyena")}><LinksProvider>
        <Paper text="一行" title="x" marks={[]} onBring={() => {}} />
      </LinksProvider></CharactersProvider>);
    expect(container.querySelector(".paper-sheet")?.getAttribute("data-size")).toBe("l");
    fireEvent.click(p.getByRole("button", { name: "小" }));
    expect(localStorage.getItem("hyenovel.paperSize")).toBe("s");
    expect(mini()).toBe("s");
  });

  it("陪讀者:每位有名字與 line;選水牛為預設,進門輸入框是水牛", async () => {
    mount();
    const p = await page();
    await go("陪讀者");
    expect(p.getAllByText("一句話")).toHaveLength(3);
    fireEvent.click(p.getByRole("radio", { name: /水牛/ }));
    expect(localStorage.getItem("hyenovel.companion")).toBe("buffalo");
    expect((p.getByRole("radio", { name: /水牛/ }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "交一篇新稿" }));
    await waitFor(() => expect(document.querySelector(".home form.composer svg.blob path.body")!.getAttribute("d")).toBe(`${blobPath("buffalo")}Z`));
  });

  it("「預設」只標在選中的那位", async () => {
    mount();
    const p = await page();
    await go("陪讀者");
    const tagged = () => p.getAllByRole("radio").filter(r => r.closest("label")!.textContent!.includes("預設"));
    expect(tagged()).toHaveLength(1);
    expect((tagged()[0] as HTMLInputElement).checked).toBe(true);
    fireEvent.click(p.getByRole("radio", { name: /鹿/ }));
    expect(tagged()).toEqual([p.getByRole("radio", { name: /鹿/ })]);
  });

  it("舊討論:只數 legacy 局,打開封存看得到逐字,沒有輸入框", async () => {
    const f = mount();
    const p = await page();
    await go("舊討論");
    await waitFor(() => expect(f.mock.calls.some(c => String(c[0]) === "/api/sessions?limit=100&legacy=1")).toBe(true));
    await waitFor(() => expect(p.getByText(/2/)).toBeTruthy());
    fireEvent.click(p.getByRole("button", { name: "打開封存" }));
    expect(p.getByText("預覽old1")).toBeTruthy();
    expect(p.getByText("預覽old2")).toBeTruthy();
    expect(p.queryByText("預覽new1")).toBeNull();
    fireEvent.click(p.getByRole("button", { name: /預覽old1/ }));
    expect(await p.findByText("舊討論的回答")).toBeTruthy();
    expect(p.getByText("我問的那句")).toBeTruthy();
    expect([...document.querySelectorAll(".dash-set-log .chat-who")].map(w => w.textContent)).toEqual(["水牛"]);
    expect(p.queryByRole("textbox")).toBeNull();
    fireEvent.click(p.getByRole("button", { name: "回清單" }));
    expect(p.getByText("預覽old2")).toBeTruthy();
  });

  it("沒有死控制項:每個分區裡沒被選中的 button/radio 點了都改變狀態;不出現未實作項目", async () => {
    mount();
    const p = await page();
    const snap = () => JSON.stringify(Object.entries(localStorage)) + document.querySelector(".dash-settings")!.innerHTML;
    const controls = () => [...document.querySelectorAll<HTMLElement>(".dash-settings button, .dash-settings input")];
    let n = 0;
    for (const sec of ["陪讀者", "舊討論", "外觀"]) {   // 外觀最後:裡面會把語言切成英文
      await go(sec);
      if (sec === "舊討論") await waitFor(() => expect(p.getByText(/2/)).toBeTruthy());
      for (let i = 0; i < controls().length; i++, n++) {
        const el = controls()[i];
        if (el.getAttribute("aria-pressed") === "true" || (el as HTMLInputElement).checked) continue;
        const before = snap();
        fireEvent.click(el);
        await waitFor(() => expect(snap()).not.toBe(before));
      }
      for (const w of ["主動先開口", "讀完開口", "用量", "資料庫"]) expect(document.querySelector(".dash-settings")!.textContent).not.toContain(w);
    }
    expect(n).toBeGreaterThan(10);
  });
});

describe("記憶頁跳回來源", () => {
  it("從設定點來源 → 到那篇的那一局,看得到逐字", async () => {
    setLang("zh-Hant");
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const u = url.split("?")[0];
      if (u === "/api/themes") return json({ themes: [olive, grass], default: "olive" });
      if (u === "/api/characters") return json({ characters: [hyena, buffalo, deer], default: "hyena" });
      if (u === "/api/works") return json({ works: [{ slug: "d1", title: "舊的", version: 1, chars: 4, updated_at: 1, state: "ready" }] });
      if (u === "/api/works/d1") return json({ slug: "d1", title: "舊的", version: 1, versions: [1], text: "內文", state: "ready", job_id: null, notes_ready: false });
      if (u === "/api/works/d1/map") return json({ version: 1, analysis_version: null, notes_version: null, beats: [], motifs: [], notes: null });
      if (u === "/api/works/d1/sessions") return json({ sessions: [
        { session: "s2", started_at: 2, last_at: 3, turns: 1, character: "hyena", mode: null, preview: "新局", version: 1, legacy: false },
        { session: "s1", started_at: 1, last_at: 2, turns: 1, character: "hyena", mode: null, preview: "舊局", version: 1, legacy: false },
      ] });
      if (u === "/api/sessions/s1") return json({ session: "s1", slug: "d1", title: "舊的", legacy: false, version: 1, turns: [
        { seq: 0, role: "user", text: "那句我說的話", ts: 1, mode: null, character: null, quotes: [], spans: [], memories: [] },
      ] });
      if (u === "/api/sessions/s2") return json({ session: "s2", slug: "d1", title: "舊的", legacy: false, version: 1, turns: [] });
      if (u === "/api/memory") return json({ memories: [{
        id: 1, root: 1, scope: "author", slug: "d1", title: "舊的", text: "記", quote: "那句", session: "s1", seq: 0,
        valid_from: 1, learned_at: 1, invalidated_at: null,
      }], caps: { author: 800, work: 600 } });
      return json({ sessions: [] });
    }));
    render(<MemoryRouter initialEntries={["/settings"]}><Where />
      <Routes><Route path="/w/:slug" element={<Dash />} /><Route path="/settings" element={<Dash />} /></Routes></MemoryRouter>);
    const nav = within(await screen.findByRole("navigation"));
    fireEvent.click(await nav.findByRole("button", { name: "記憶" }));
    fireEvent.click(await screen.findByRole("link", { name: "那句" }));
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/w/d1"));
    expect(await within(await screen.findByRole("log")).findByText("那句我說的話")).toBeTruthy();
  });
});
