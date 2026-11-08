import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import Dash from "../src/dash/Dash";
import Paper from "../src/dash/Paper";
import { loadPaperFlow, setPaperFlow } from "../src/dash/paperFlow";
import { en, setLang, zhHant } from "../src/dash/i18n";
import { getThemeState, setMode } from "../src/dash/theme";
import { LinksProvider } from "../src/dash/links";
import { CharactersProvider, makeCharacters } from "../src/dash/useCharacters";
import type { Character } from "../src/dash/api";
import { companionId } from "../src/dash/useTalk";
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
    { role: "user", text: "我問的那句", ts: 1, character: null, quotes: [], spans: [] },
    { role: "assistant", text: "舊討論的回答", ts: 2, character: "buffalo", quotes: [], spans: [] },
    { role: "user", text: "再問", ts: 3, character: null, quotes: [], spans: [] },
    { role: "assistant", text: "同一位再答", ts: 4, character: "buffalo", quotes: [], spans: [] },
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
type Q = ReturnType<typeof within>;
const card = (p: Q, name: string) => p.getByRole("button", { name: `打開${name}` });
const isDefault = (p: Q, name: string) => card(p, name).getAttribute("data-on") === "true";
const sheet = (p: Q, name: string) => { fireEvent.click(card(p, name)); return within(p.getByRole("dialog", { name })); };

describe("設定頁", () => {
  it("在 /settings:書架沒有作品清單與篩選框,有回去鍵與三個分區", async () => {
    mount();
    const nav = await shelf();
    expect(nav.queryByText("舊的")).toBeNull();
    expect(nav.queryByRole("searchbox")).toBeNull();
    const names = within(nav.getByRole("group", { name: "設定分區" })).getAllByRole("button").map(b => b.getAttribute("aria-label"));
    expect(names).toEqual(["返回", "外觀", "讀伴", "記憶", "舊討論"]);
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
  it("settings back button reads 返回:沒開過作品到 /,開過〈舊的〉回 /w/d1", async () => {
    mount();
    await go("返回");
    expect(screen.getByTestId("loc").textContent).toBe("/");
    await go("展開書架");
    fireEvent.click((await shelf()).getByRole("button", { name: /^舊的/ }));
    expect(screen.getByTestId("loc").textContent).toBe("/w/d1");
    await go("設定");
    await go("返回");
    expect(screen.getByTestId("loc").textContent).toBe("/w/d1");
  });
  it("點「讀伴」→ 內容換成讀伴卡片;外觀沒有預覽卡", async () => {
    mount();
    const p = await page();
    expect(p.queryByRole("figure")).toBeNull();
    await go("讀伴");
    expect(p.getAllByRole("button", { name: /^打開/ })).toHaveLength(3);
    expect(p.getByRole("heading", { level: 1, name: "讀伴" })).toBeTruthy();
  });
  it("配色只放色票(亮、暗各半),名字只在 aria-label", async () => {
    mount();
    const p = await page();
    const seg = within(p.getByRole("group", { name: "配色" }));
    const btns = seg.getAllByRole("button");
    expect(btns.length).toBeGreaterThan(0);
    for (const b of btns) {
      expect(b.textContent).toBe("");
      expect(b.getAttribute("aria-label")).toBeTruthy();
      expect(b.querySelectorAll(".set-scene > span")).toHaveLength(2);
    }
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

  it("字級是三個大小不同的「字」;存 localStorage,Paper 套 data-size", async () => {
    mount();
    const p = await page();
    const big = p.getByRole("button", { name: "大" });
    expect(big.textContent).toBe("字");
    expect(big.querySelector(".set-glyph")!.getAttribute("data-size")).toBe("l");
    fireEvent.click(big);
    expect(localStorage.getItem("hyenovel.paperSize")).toBe("l");
    expect(big.getAttribute("aria-pressed")).toBe("true");
    const { container } = render(
      <CharactersProvider value={makeCharacters([hyena], "hyena")}><LinksProvider>
        <Paper text="一行" title="x" marks={[]} onBring={() => {}} />
      </LinksProvider></CharactersProvider>);
    expect(container.querySelector(".paper-sheet")?.getAttribute("data-size")).toBe("l");
    fireEvent.click(p.getByRole("button", { name: "小" }));
    expect(localStorage.getItem("hyenovel.paperSize")).toBe("s");
  });

  it("讀伴:den 存好預設才讓開著的對話跟著換", async () => {
    const f = mount();
    const base = f.getMockImplementation()!;
    let release = () => {};
    const gate = new Promise<void>(r => { release = r; });
    f.mockImplementation(async (u: string, ...rest: unknown[]) => {
      if (u === "/api/characters/default") await gate;
      return (base as (...a: unknown[]) => Promise<Response>)(u, ...rest);
    });
    const p = await page();
    await go("讀伴");
    fireEvent.click(sheet(p, "水牛").getByRole("button", { name: "設為預設" }));
    expect(companionId(makeCharacters([hyena, buffalo, deer], "hyena"))).toBe("hyena");
    release();
    await waitFor(() => expect(companionId(makeCharacters([hyena, buffalo, deer], "hyena"))).toBe("buffalo"));
  });
  it("讀伴:den 存不下預設時,選取退回原角色並顯示錯誤", async () => {
    const f = mount();
    const base = f.getMockImplementation()!;
    f.mockImplementation(async (u: string, ...rest: unknown[]) =>
      u === "/api/characters/default"
        ? new Response(JSON.stringify({ detail: "x", code: "unknown-character", params: {} }), { status: 422 })
        : (base as (...a: unknown[]) => Promise<Response>)(u, ...rest));
    const p = await page();
    await go("讀伴");
    fireEvent.click(sheet(p, "水牛").getByRole("button", { name: "設為預設" }));
    expect(await p.findByRole("alert")).toBeTruthy();
    expect(isDefault(p, "鬣狗")).toBe(true);
    expect(isDefault(p, "水牛")).toBe(false);
  });
  it("讀伴:每位有名字與 line;選水牛為預設,進門輸入框是水牛", async () => {
    mount();
    const p = await page();
    await go("讀伴");
    expect(p.getAllByText("一句話")).toHaveLength(3);
    fireEvent.click(sheet(p, "水牛").getByRole("button", { name: "設為預設" }));
    expect(isDefault(p, "水牛")).toBe(true);
    fireEvent.keyDown(p.getByRole("dialog"), { key: "Escape" });
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([u, i]) =>
      u === "/api/characters/default" && i?.method === "PUT" && i.body === JSON.stringify({ character: "buffalo" }))).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: "開一局聊天" }));
    await waitFor(() => expect(document.querySelector(".home form.composer svg.fig")!.getAttribute("data-who")).toBe("buffalo"));
  });

  it("「預設」只標在選中的那位", async () => {
    mount();
    const p = await page();
    await go("讀伴");
    const tagged = () => p.getAllByRole("button", { name: /^打開/ }).filter(b => b.querySelector(".char-tag")?.textContent === "預設");
    expect(tagged()).toEqual([card(p, "鬣狗")]);
    const s = sheet(p, "鹿");
    fireEvent.click(s.getByRole("button", { name: "設為預設" }));
    expect(tagged()).toEqual([card(p, "鹿")]);
    expect(s.getByRole("button", { name: "預設" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("舊討論:只數 legacy 局,進來就列出,看得到逐字,沒有輸入框", async () => {
    const f = mount();
    const p = await page();
    await go("舊討論");
    await waitFor(() => expect(f.mock.calls.some(c => String(c[0]) === "/api/sessions?limit=100&legacy=1")).toBe(true));
    await waitFor(() => expect(p.getByText("2 局")).toBeTruthy());
    expect(p.getByText("2 局")).toBeTruthy();
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

  it("封存的局:列在舊討論頁上方,可拉回;永久刪除要再確認一次", async () => {
    const f = mount();
    const base = f.getMockImplementation()!;
    const sent: string[] = [];
    f.mockImplementation(async (u: string, init?: RequestInit) => {
      if (u === "/api/archived-sessions") return json({ sessions: [
        { session: "a1", slug: "d1", title: "舊的", preview: "封存一", last_at: 2, archived_at: 3 },
        { session: "a2", slug: null, title: null, preview: "封存二", last_at: 2, archived_at: 3 }] });
      if (init?.method === "POST" || init?.method === "DELETE") { sent.push(`${init.method} ${u}`); return new Response(null, { status: 204 }); }
      return (base as (u: string, i?: RequestInit) => Promise<Response>)(u, init);
    });
    const p = await page();
    await go("舊討論");
    const box = within(await p.findByRole("region", { name: "封存的局" }));
    expect(box.getByText("封存一")).toBeTruthy();
    expect(p.getByText("改版前的討論")).toBeTruthy();
    fireEvent.click(box.getAllByRole("button", { name: "拉回" })[0]);
    await waitFor(() => expect(box.queryByText("封存一")).toBeNull());
    fireEvent.click(box.getByRole("button", { name: "永久刪除" }));
    expect(sent).toEqual(["POST /api/sessions/a1/unarchive"]);
    expect(box.getByText(/確定永久刪除/)).toBeTruthy();
    fireEvent.click(box.getByRole("button", { name: "取消" }));
    expect(box.getByText("封存二")).toBeTruthy();
    fireEvent.click(box.getByRole("button", { name: "永久刪除" }));
    fireEvent.click(within(box.getByRole("group", { name: "永久刪除" })).getByRole("button", { name: "永久刪除" }));
    await waitFor(() => expect(p.queryByRole("region", { name: "封存的局" })).toBeNull());
    expect(sent).toEqual(["POST /api/sessions/a1/unarchive", "DELETE /api/sessions/a2"]);
  });

  it("舊討論依作品分組,預覽去掉 markdown 記號", async () => {
    const f = mount();
    const base = f.getMockImplementation()!;
    f.mockImplementation(async (u: string, ...rest: unknown[]) =>
      u.startsWith("/api/sessions?")
        ? json({ sessions: [row("a", true), { ...row("b", true), slug: "d2", title: "長夜", preview: "**粗體**與`碼`" }, row("c", true)] })
        : (base as (...a: unknown[]) => Promise<Response>)(u, ...rest));
    const p = await page();
    await go("舊討論");
    const sea = within(await p.findByRole("region", { name: "舊的" }));
    expect(sea.getAllByRole("button").map(b => b.querySelector("span")!.textContent)).toEqual(["預覽a", "預覽c"]);
    expect(within(p.getByRole("region", { name: "長夜" })).getByText("粗體與碼")).toBeTruthy();
  });
  it("讀伴面板:點外面關,焦點回到卡片", async () => {
    mount();
    const p = await page();
    await go("讀伴");
    card(p, "鹿").focus();
    const s = sheet(p, "鹿");
    expect(document.activeElement).toBe(s.getByRole("button", { name: "關" }));
    fireEvent.click(document.querySelector(".char-veil")!);
    expect(p.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(card(p, "鹿"));
  });

  it("沒有死控制項:每個分區裡沒被選中的 button/radio 點了都改變狀態;不出現未實作項目", async () => {
    mount();
    const p = await page();
    const snap = () => JSON.stringify(Object.entries(localStorage)) + document.querySelector(".dash-settings")!.innerHTML;
    const controls = () => [...document.querySelectorAll<HTMLElement>(".dash-settings button, .dash-settings input")]
      .filter(el => !["匯入", "新角色"].includes(el.getAttribute("aria-label") ?? el.textContent ?? "")
        && !/^(複製|編輯)/.test(el.getAttribute("aria-label") ?? ""));   // 系統檔案視窗不改狀態;新角色、複製、編輯另有測試
    let n = 0;
    for (const sec of ["讀伴", "舊討論", "外觀"]) {   // 外觀最後:裡面會把語言切成英文
      await go(sec);
      if (sec === "舊討論") await waitFor(() => expect(p.getByText("2 局")).toBeTruthy());
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
        { session: "s2", started_at: 2, last_at: 3, turns: 1, character: "hyena", preview: "新局", version: 1, legacy: false },
        { session: "s1", started_at: 1, last_at: 2, turns: 1, character: "hyena", preview: "舊局", version: 1, legacy: false },
      ] });
      if (u === "/api/sessions/s1") return json({ session: "s1", slug: "d1", title: "舊的", legacy: false, version: 1, turns: [
        { seq: 0, role: "user", text: "那句我說的話", ts: 1, character: null, quotes: [], spans: [], memories: [] },
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

describe("設定頁:角色卡", () => {
  let list: Character[];
  let posts: { card: unknown; confirm: boolean }[];
  let reply: (confirm: boolean) => Response;
  let edits: { name: Record<string, string>; line: Record<string, string>; reading: string; confirm: boolean }[];
  let editReply: (confirm: boolean) => Response;
  let listFails: boolean;
  const imported = { ...deer, id: "u1", origin: "imported" as const, name: { "zh-Hant": "老讀", en: "Old" } };
  const mountCards = () => {
    const f = vi.fn(async (u: string, init?: RequestInit) => {
      if (u === "/api/themes") return json({ themes: [olive], default: "olive" });
      if (u === "/api/characters" && listFails) return new Response("{}", { status: 500 });
      if (u === "/api/characters") return json({ characters: list, default: "hyena" });
      if (u === "/api/characters/import") {
        const b = JSON.parse(String(init?.body));
        posts.push(b);
        return reply(b.confirm);
      }
      if (u === "/api/characters/hyena/copy") {
        list = [...list, { ...hyena, id: "c1", origin: "created", name: { "zh-Hant": "鬣狗(副本)", en: "Hyena (copy)" } }];
        return json({ character: list[list.length - 1] });
      }
      if (u === "/api/characters/u1" && init?.method === "PATCH") {
        const b = JSON.parse(String(init.body));
        edits.push(b);
        const r = editReply(b.confirm);
        if (r.status === 200) list = list.map(c => c.id === "u1" ? { ...c, name: b.name, line: b.line, reading: b.reading } : c);
        return r;
      }
      if (u === "/api/characters/u1" && init?.method === "DELETE") {
        list = list.map(c => c.id === "u1" ? { ...c, archived: true } : c);
        return json({ archived: "u1" });
      }
      if (u === "/api/works") return json({ works: [] });
      return json({ sessions: [] });
    });
    vi.stubGlobal("fetch", f);
    render(<MemoryRouter initialEntries={["/settings"]}><Routes><Route path="/settings" element={<Dash />} /></Routes></MemoryRouter>);
  };
  const upload = async (content: string) => {
    const input = (await screen.findByLabelText("匯入", { selector: "input" })) as HTMLInputElement;
    const file = new File([content], "card.json", { type: "application/json" });
    Object.defineProperty(file, "text", { value: async () => content });
    fireEvent.change(input, { target: { files: [file] } });
  };
  const open = async () => { setLang("zh-Hant"); await go("讀伴"); return page(); };
  beforeEach(() => {
    list = [hyena, imported]; posts = []; edits = []; listFails = false;
    reply = () => json({ imported: true, character: imported, warnings: [] });
    editReply = () => json({ edited: true, character: imported });
  });

  it("新角色鈕打開問卷,回去回到清單", async () => {
    mountCards();
    const p = await open();
    fireEvent.click(p.getByRole("button", { name: "新角色" }));
    expect(p.getByLabelText("陪你讀稿的,是什麼?")).toBeTruthy();
    fireEvent.click(p.getByRole("button", { name: "回讀伴" }));
    expect(p.getByRole("button", { name: "新角色" })).toBeTruthy();
  });
  it("內建角色沒有封存鈕,匯入的角色有;每位都能匯出", async () => {
    mountCards();
    const p = await open();
    const h = sheet(p, "鬣狗");
    expect(h.queryByRole("button", { name: "封存鬣狗" })).toBeNull();
    expect(h.getByRole("link", { name: "匯出鬣狗" }).getAttribute("href")).toBe("/api/characters/hyena/card");
    fireEvent.click(h.getByRole("button", { name: "關" }));
    expect(sheet(p, "老讀").getByRole("button", { name: "封存老讀" })).toBeTruthy();
  });
  it("內建角色沒有編輯鈕但有複製鈕;匯入的兩個都有", async () => {
    mountCards();
    const p = await open();
    const h = sheet(p, "鬣狗");
    expect(h.queryByRole("button", { name: "編輯鬣狗" })).toBeNull();
    expect(h.getByRole("button", { name: "複製鬣狗" })).toBeTruthy();
    fireEvent.keyDown(p.getByRole("dialog"), { key: "Escape" });
    expect(p.queryByRole("dialog")).toBeNull();
    const o = sheet(p, "老讀");
    expect(o.getByRole("button", { name: "編輯老讀" })).toBeTruthy();
    expect(o.getByRole("button", { name: "複製老讀" })).toBeTruthy();
  });
  it("複製後清單多一位副本", async () => {
    mountCards();
    const p = await open();
    fireEvent.click(sheet(p, "鬣狗").getByRole("button", { name: "複製鬣狗" }));
    expect(await p.findByText("鬣狗(副本)")).toBeTruthy();
  });
  it("編輯:卡片換成編輯器,只改目前語言,存完清單更新", async () => {
    mountCards();
    const p = await open();
    fireEvent.click(sheet(p, "老讀").getByRole("button", { name: "編輯老讀" }));
    expect(p.queryByRole("dialog")).toBeNull();
    expect((p.getByLabelText("讀法") as HTMLTextAreaElement).value).toBe(imported.reading);
    expect(p.queryByRole("button", { name: "打開老讀" })).toBeNull();
    fireEvent.change(p.getByLabelText("名字"), { target: { value: "新老讀" } });
    fireEvent.click(p.getByRole("button", { name: "存" }));
    expect(await p.findByRole("button", { name: "打開新老讀" })).toBeTruthy();
    expect(edits).toEqual([{ name: { "zh-Hant": "新老讀", en: "Old" }, line: imported.line, reading: imported.reading, confirm: false }]);
    expect(p.queryByLabelText("讀法")).toBeNull();
  });
  it("已經存好但清單重抓失敗時,編輯器仍關掉,不會誘使再存一次", async () => {
    mountCards();
    const p = await open();
    fireEvent.click(sheet(p, "老讀").getByRole("button", { name: "編輯老讀" }));
    listFails = true;
    fireEvent.click(p.getByRole("button", { name: "存" }));
    await waitFor(() => expect(p.queryByLabelText("讀法")).toBeNull());
    expect(edits).toHaveLength(1);
  });
  it("編輯有警告要確認;取消回卡片", async () => {
    editReply = confirm => confirm ? json({ edited: true, character: imported }) : json({ edited: false, warnings: ["looks-like-instructions"] });
    mountCards();
    const p = await open();
    fireEvent.click(sheet(p, "老讀").getByRole("button", { name: "編輯老讀" }));
    fireEvent.click(p.getByRole("button", { name: "存" }));
    fireEvent.click(await p.findByRole("button", { name: "仍要存" }));
    await waitFor(() => expect(edits.map(e => e.confirm)).toEqual([false, true]));
    await waitFor(() => expect(p.queryByLabelText("讀法")).toBeNull());
    fireEvent.click(sheet(p, "老讀").getByRole("button", { name: "編輯老讀" }));
    fireEvent.click(p.getByRole("button", { name: "取消" }));
    expect(card(p, "老讀")).toBeTruthy();
  });
  it("匯入有警告時先列出,確認才送第二次", async () => {
    list = [hyena];
    reply = confirm => confirm ? json({ imported: true, character: imported, warnings: ["ignored-fields"] })
      : json({ imported: false, warnings: ["ignored-fields"] });
    mountCards();
    const p = await open();
    await upload(JSON.stringify({ spec: "chara_card_v3" }));
    expect(await p.findByText(zhHant["card.warn.ignored-fields"])).toBeTruthy();
    expect(posts).toEqual([{ card: { spec: "chara_card_v3" }, confirm: false }]);
    list = [hyena, imported];
    fireEvent.click(p.getByRole("button", { name: "仍要匯入" }));
    expect(await p.findByRole("button", { name: "打開老讀" })).toBeTruthy();
    expect(posts[1].confirm).toBe(true);
    expect(p.queryByText(zhHant["card.warn.ignored-fields"])).toBeNull();
  });
  it("警告可以取消,不送第二次", async () => {
    reply = () => json({ imported: false, warnings: ["newer-spec"] });
    mountCards();
    const p = await open();
    await upload("{}");
    fireEvent.click(await p.findByRole("button", { name: "取消" }));
    await waitFor(() => expect(p.queryByText(zhHant["card.warn.newer-spec"])).toBeNull());
    expect(posts).toHaveLength(1);
  });
  it("檔案不是 JSON 時顯示錯誤,不送請求", async () => {
    mountCards();
    const p = await open();
    await upload("not json");
    expect(await p.findByText(zhHant["card.err.not-json"])).toBeTruthy();
    expect(posts).toHaveLength(0);
  });
  it("den 擋下的卡逐條顯示原因", async () => {
    reply = () => new Response(JSON.stringify({ detail: "x", code: "bad-card", params: { errors: ["no-reading"] } }), { status: 422 });
    mountCards();
    const p = await open();
    await upload("{}");
    expect(await p.findByText(zhHant["card.err.no-reading"])).toBeTruthy();
  });
  it("封存後從選單消失", async () => {
    mountCards();
    const p = await open();
    fireEvent.click(sheet(p, "老讀").getByRole("button", { name: "封存老讀" }));
    expect(p.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(p.queryByRole("button", { name: "打開老讀" })).toBeNull());
    expect(card(p, "鬣狗")).toBeTruthy();
  });
  it("每個代碼都有中英文案", () => {
    for (const code of ["bad-schema", "too-large", "name-too-long", "reading-too-long", "no-reading", "not-json"]) {
      expect(zhHant[`card.err.${code}` as keyof typeof zhHant]).toBeTruthy();
      expect(en[`card.err.${code}` as keyof typeof en]).toBeTruthy();
    }
    for (const code of ["newer-spec", "looks-like-instructions", "ignored-fields", "bad-colors", "bad-figure"]) {
      expect(zhHant[`card.warn.${code}` as keyof typeof zhHant]).toBeTruthy();
      expect(en[`card.warn.${code}` as keyof typeof en]).toBeTruthy();
    }
  });
});
