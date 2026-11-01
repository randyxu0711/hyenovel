import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within, act } from "@testing-library/react";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import Dash from "../src/dash/Dash";
import { setLang } from "../src/dash/i18n";
import { DRAW_MS } from "../src/dash/Paper";
import { olive, hyena, buffalo, deer } from "./dash-fixtures";

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
const sse = (...evs: [string, unknown][]) => new Response(new ReadableStream({
  start(c) {
    const enc = new TextEncoder();
    for (const [event, data] of evs) c.enqueue(enc.encode(`data: ${JSON.stringify({ event, data })}\n\n`));
    c.close();
  },
}));
type Span = { quote: string; start: number | null; end: number | null };
const works = [{ slug: "d1", title: "海", version: 1, chars: 4 }];
let talkBodies: any[];
let talkReply: () => Response;
let sessions: Record<string, object>;
let rows: object[];
let text: string;
let versions: number[];

const a = (t: string, character: string | null, spans: Span[] = [], mode: string | null = null) =>
  ({ role: "assistant", text: t, ts: 1, mode, character, quotes: [], spans });
const u = (t: string, quotes: string[] = []) => ({ role: "user", text: t, ts: 1, mode: null, character: null, quotes, spans: [] });
const session = (id: string, turns: object[], over: object = {}) => { sessions[id] = { session: id, slug: "d1", title: "海", turns, legacy: false, version: 1, ...over }; };
const row = (id: string, over: object = {}) => ({ session: id, started_at: 1, last_at: 2, turns: 2, character: "buffalo", mode: "direct", preview: "q1", version: 1, legacy: false, ...over });

function mount(path = "/w/d1", chars = [hyena, buffalo, deer]) {
  const f = vi.fn(async (url: string, init?: RequestInit) => {
    const [p, q] = url.split("?");
    const v = q?.startsWith("v=") ? Number(q.slice(2)) : null;
    if (p === "/api/themes") return json({ themes: [olive], default: "olive" });
    if (p === "/api/characters") return json({ characters: chars, default: "hyena" });
    if (p === "/api/works") return json({ works });
    if (p === "/api/works/d1") return json({ slug: "d1", title: "海", version: v ?? Math.max(...versions), versions, text, state: "ready", job_id: null, notes_ready: false });
    if (p === "/api/works/d1/map") return json({ version: v ?? 1, analysis_version: null, notes_version: null, beats: [], motifs: [], notes: null });
    if (p === "/api/works/d1/sessions") return json({ sessions: rows });
    if (p.startsWith("/api/discuss/")) { talkBodies.push(JSON.parse(String(init?.body))); return talkReply(); }
    if (p.startsWith("/api/sessions/")) return json(sessions[decodeURIComponent(p.split("/").pop()!)]);
    return json({ sessions: [] });
  });
  vi.stubGlobal("fetch", f);
  return render(<MemoryRouter initialEntries={[path]}><Where />
    <Routes><Route path="/w/:slug" element={<Dash />} /><Route path="/settings" element={<Dash />} /></Routes></MemoryRouter>);
}
function Where() { const l = useLocation(); return <output data-testid="loc">{l.pathname}{l.search}</output>; }
const loc = () => screen.getByTestId("loc").textContent;
const whoKey = () => screen.getByRole("button", { name: "陪讀者" });
const reply = (t: string, character = "hyena", sid = "s1", spans: Span[] = []) => () => sse(
  ["token", { text: t.slice(0, 1) }], ["token", { text: t.slice(1) }],
  ["message", { role: "assistant", text: t, session_id: sid, mode: "slow", character, spans }], ["done", { ok: true, session_id: sid }]);
const say = (s: string) => {
  fireEvent.change(screen.getByLabelText("對話輸入"), { target: { value: s } });
  fireEvent.click(screen.getByRole("button", { name: "送出" }));
};
const calls = () => ((fetch as unknown as ReturnType<typeof vi.fn>).mock.calls as [string][]).map(c => c[0]);
const log = () => within(screen.getByRole("log"));
const findLog = async () => within(await screen.findByRole("log"));

beforeEach(() => {
  setLang("zh-Hant"); localStorage.clear(); talkBodies = []; talkReply = reply("嗯"); sessions = {}; rows = [];
  text = "第一段。"; versions = [1];
});
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers(); });

describe("選人", () => {
  it("在輸入框的陪讀者選單選過的角色會被記住", async () => {
    const { unmount } = mount();
    const pick = async () => {
      fireEvent.click(await screen.findByRole("button", { name: "陪讀者" }));
      return within(screen.getByRole("group", { name: "陪讀者" })).getByRole("button", { name: "水牛" });
    };
    fireEvent.click(await pick());
    expect((await pick()).getAttribute("aria-pressed")).toBe("true");
    unmount();
    mount();
    expect((await pick()).getAttribute("aria-pressed")).toBe("true");
  });
  it("沒選過人時打開既有的局:直接看逐字,接著由最後說話的那位陪讀", async () => {
    rows = [row("s1")];
    session("s1", [u("你好"), a("我是水牛", "buffalo")]);
    mount();
    expect(await (await findLog()).findByText("我是水牛")).toBeTruthy();
    say("接著聊");
    await waitFor(() => expect(talkBodies[0]).toMatchObject({ character: "buffalo", session_id: "s1" }));
  });
  it("記住的角色不在清單時退回預設", async () => {
    localStorage.setItem("hyenovel.companion", "ghost");
    mount();
    await screen.findByLabelText("對話輸入");
    say("嗨");
    await waitFor(() => expect(talkBodies[0].character).toBe("hyena"));
  });
});

describe("換預設陪讀者在作品頁立即生效", () => {
  it("作品頁 ⌘K 選「陪讀者:水牛」→ 輸入框旁換成水牛,下一輪送給水牛", async () => {
    mount();
    await screen.findByText("第一段。");
    expect(whoKey().textContent).toContain("鬣狗");
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    fireEvent.click(within(await screen.findByRole("dialog", { name: "指令框" })).getByRole("option", { name: "陪讀者:水牛" }));
    await waitFor(() => expect(whoKey().textContent).toContain("水牛"));
    say("嗨");
    await waitFor(() => expect(talkBodies[0]?.character).toBe("buffalo"));
  });
  it("設定頁改預設為鹿(之前記的是水牛)→ 再打開沒有局的作品,由鹿接話", async () => {
    localStorage.setItem("hyenovel.companion", "buffalo");
    mount("/w/d1");
    await screen.findByText("第一段。");
    expect(whoKey().textContent).toContain("水牛");
    fireEvent.click(screen.getByRole("button", { name: "設定" }));
    fireEvent.click(await screen.findByRole("radio", { name: /鹿/ }));
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    fireEvent.click(within(await screen.findByRole("dialog", { name: "指令框" })).getByRole("option", { name: "作品:海" }));
    await screen.findByText("第一段。");
    expect(whoKey().textContent).toContain("鹿");
    say("嗨");
    await waitFor(() => expect(talkBodies[0]?.character).toBe("deer"));
  });
});

describe("對話", () => {
  beforeEach(() => localStorage.setItem("hyenovel.companion", "buffalo"));
  it("送出帶 character,帶著的引文送進 quotes 並顯示在訊息上", async () => {
    mount();
    await screen.findByText("第一段。");
    const p = screen.getByText("第一段。").firstChild!;
    const range = document.createRange(); range.setStart(p, 0); range.setEnd(p, 3);
    document.getSelection()!.removeAllRanges(); document.getSelection()!.addRange(range);
    act(() => { document.dispatchEvent(new Event("selectionchange")); });
    fireEvent.click(await screen.findByRole("button", { name: "帶進對話" }));
    say("這段怎麼樣");
    await screen.findByText("嗯");
    expect(talkBodies[0]).toMatchObject({ character: "buffalo", quotes: ["第一段"], message: "這段怎麼樣", session_id: null });
    expect(log().getByText("第一段")).toBeTruthy();
    expect(log().getByText("這段怎麼樣")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "拿掉這段引文" })).toBeNull();
  });
  it("token 逐段接上、沒有計時器;第一個 token 前說「X 在讀你的稿」;message 到了換成正式訊息並標說話者", async () => {
    let release!: () => void, start!: () => void;
    const gate = new Promise<void>(r => { release = r; });
    const first = new Promise<void>(r => { start = r; });
    talkReply = () => new Response(new ReadableStream({
      async start(c) {
        const enc = new TextEncoder();
        const w = (event: string, data: unknown) => c.enqueue(enc.encode(`data: ${JSON.stringify({ event, data })}\n\n`));
        await first;
        w("token", { text: "半" });
        await gate;
        w("token", { text: "句" });
        w("message", { role: "assistant", text: "半句", session_id: "s1", mode: "direct", character: "buffalo", spans: [] });
        w("done", { ok: true, session_id: "s1" });
        c.close();
      },
    }));
    mount();
    await screen.findByText("第一段。");
    // jsdom 寫 localStorage 時會用 setTimeout 發 storage 事件(不是我們的計時器):這一則不需要真的存
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {});
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {});
    vi.useFakeTimers();
    const flush = async (until: () => boolean) => {
      for (let i = 0; i < 200 && !until(); i++) await act(async () => { await Promise.resolve(); });
    };
    say("嗨");
    await flush(() => !!screen.queryByText("水牛在讀你的稿"));
    expect(screen.getByText("水牛在讀你的稿").closest("[role=status]")).toBeTruthy();
    start();
    await flush(() => !!screen.queryByText("半"));
    expect(screen.getByText("半")).toBeTruthy();
    expect(screen.queryByText("水牛在讀你的稿")).toBeNull();
    expect(vi.getTimerCount()).toBe(0);   // 串流中沒有任何排程計時器
    release();
    await flush(() => !!screen.queryByText("半句"));
    expect(log().getByText("半句")).toBeTruthy();
    expect(log().getByText("水牛")).toBeTruthy();
    expect(vi.getTimerCount()).toBe(0);
  });
  it("說話者換人時有分隔線;舊局沒有 character 時用同 mode 的角色標示", async () => {
    rows = [row("s1")];
    session("s1", [u("一"), a("我先讀", null, [], "slow"), u("二"), a("換我", "buffalo")]);
    mount();
    await (await findLog()).findByText("換我");
    expect(log().getByText("鬣狗")).toBeTruthy();
    const sep = log().getAllByRole("separator");
    expect(sep.map(s => s.textContent)).toEqual(["換水牛來讀"]);
  });
  it("409 busy 顯示訊息且輸入框保留原字", async () => {
    talkReply = () => json({ detail: "busy", code: "busy" }, 409);
    mount();
    await screen.findByText("第一段。");
    say("還沒說完的話");
    expect((await screen.findByRole("alert")).textContent).toBe("這一局還有一輪在進行,稍等一下。");
    expect((screen.getByLabelText("對話輸入") as HTMLTextAreaElement).value).toBe("還沒說完的話");
  });
  it("沒送出的草稿依作品存著,重掛載後還在;送出成功後清掉", async () => {
    const { unmount } = mount();
    fireEvent.change(await screen.findByLabelText("對話輸入"), { target: { value: "寫到一半" } });
    expect(localStorage.getItem("hyenovel.draft.d1")).toBe("寫到一半");
    unmount();
    mount();
    expect((await screen.findByLabelText("對話輸入") as HTMLTextAreaElement).value).toBe("寫到一半");
    fireEvent.click(screen.getByRole("button", { name: "送出" }));
    await (await findLog()).findByText("嗯");
    expect(localStorage.getItem("hyenovel.draft.d1")).toBeNull();
  });
  it("打開作品頁與收到每則 message 都更新 hyenovel.seen", async () => {
    mount();
    await screen.findByText("第一段。");
    expect(JSON.parse(localStorage.getItem("hyenovel.seen")!).d1).toBeTypeOf("number");
    localStorage.removeItem("hyenovel.seen");
    say("嗨");
    await (await findLog()).findByText("嗯");
    expect(JSON.parse(localStorage.getItem("hyenovel.seen")!).d1).toBeTypeOf("number");
  });
});

describe("局選單", () => {
  it("列出時間、誰、第一句話;點「新的一局」→ 下次送出 session_id 是 null", async () => {
    const at = new Date(2026, 9, 31, 21, 40).getTime() / 1000;
    rows = [row("s1", { last_at: at, preview: "第一句話" })];
    session("s1", [u("第一句話"), a("水牛說", "buffalo")]);
    mount();
    await (await findLog()).findByText("水牛說");
    fireEvent.click(screen.getByRole("button", { name: /換一局/ }));
    const list = within(screen.getByRole("group", { name: "這篇的對話" }));
    const item = list.getByRole("button", { name: /第一句話/ });
    expect(item.textContent).toContain("21:40");
    expect(item.textContent).toContain("水牛");
    expect(item.getAttribute("aria-current")).toBe("true");
    fireEvent.click(list.getByRole("button", { name: "新的一局" }));
    expect(log().queryByText("水牛說")).toBeNull();
    say("重來");
    await waitFor(() => expect(talkBodies[0].session_id).toBeNull());
  });
  it("從選單打開別的局", async () => {
    rows = [row("s2", { last_at: 9, preview: "新的" }), row("s1", { last_at: 3, preview: "舊的" })];
    session("s2", [u("新的"), a("後來的話", "buffalo")]);
    session("s1", [u("舊的"), a("以前的話", "hyena")]);
    mount();
    await (await findLog()).findByText("後來的話");
    fireEvent.click(screen.getByRole("button", { name: /換一局/ }));
    fireEvent.click(within(screen.getByRole("group", { name: "這篇的對話" })).getByRole("button", { name: /舊的/ }));
    expect(await (await findLog()).findByText("以前的話")).toBeTruthy();
    say("續");
    await waitFor(() => expect(talkBodies[0]).toMatchObject({ session_id: "s1", character: "hyena" }));
  });
  it("選了舊的局 → 網址記 ?s=;重掛載這個網址回到同一局,下一輪接著它", async () => {
    rows = [row("s2", { last_at: 9, preview: "新的" }), row("s1", { last_at: 3, preview: "舊的" })];
    session("s2", [u("新的"), a("後來的話", "buffalo")]);
    session("s1", [u("舊的"), a("以前的話", "hyena")]);
    const { unmount } = mount();
    await (await findLog()).findByText("後來的話");
    fireEvent.click(screen.getByRole("button", { name: /換一局/ }));
    fireEvent.click(within(screen.getByRole("group", { name: "這篇的對話" })).getByRole("button", { name: /舊的/ }));
    await (await findLog()).findByText("以前的話");
    expect(loc()).toBe("/w/d1?s=s1");
    unmount();
    mount("/w/d1?s=s1");
    expect(await (await findLog()).findByText("以前的話")).toBeTruthy();
    expect(log().queryByText("後來的話")).toBeNull();
    say("續");
    await waitFor(() => expect(talkBodies[0]).toMatchObject({ session_id: "s1" }));
  });
  it("「新的一局」拿掉 ?s=;新局送出後記成新局;換版本保留 ?s=", async () => {
    versions = [1, 2];
    rows = [row("s1")];
    session("s1", [u("q1"), a("水牛說", "buffalo")]);
    talkReply = reply("嗯", "hyena", "s7");
    mount("/w/d1?s=s1");
    await (await findLog()).findByText("水牛說");
    fireEvent.click(screen.getByRole("button", { name: /換一局/ }));
    fireEvent.click(within(screen.getByRole("group", { name: "這篇的對話" })).getByRole("button", { name: "新的一局" }));
    expect(loc()).toBe("/w/d1");
    say("重來");
    await (await findLog()).findByText("嗯");
    expect(loc()).toBe("/w/d1?s=s7");
    session("s7", [u("重來"), a("嗯", "hyena")]);
    fireEvent.click(screen.getByRole("button", { name: "v1" }));
    expect(new URLSearchParams(loc()!.split("?")[1]).get("s")).toBe("s7");
    expect(new URLSearchParams(loc()!.split("?")[1]).get("v")).toBe("1");
  });
  it("?s= 指的局不在這篇的清單裡 → 照常打開最近那局", async () => {
    rows = [row("s2", { last_at: 9 })];
    session("s2", [u("新的"), a("後來的話", "buffalo")]);
    mount("/w/d1?s=nope");
    expect(await (await findLog()).findByText("後來的話")).toBeTruthy();
  });
  it("legacy 局:看得到逐字,輸入框 disabled 並說明", async () => {
    rows = [row("s9")];
    session("s9", [u("舊問題"), a("批評家的話", null)], { legacy: true });
    mount();
    await (await findLog()).findByText("批評家的話");
    expect((screen.getByLabelText("對話輸入") as HTMLTextAreaElement).disabled).toBe(true);
    expect(screen.getByText("這是改版前的舊討論,只能看,不能接著聊。")).toBeTruthy();
  });
});

describe("引文", () => {
  beforeEach(() => { text = "海很藍。第二句。"; });
  const withQuote = (spans: Span[]) => {
    rows = [row("s1")];
    session("s1", [u("看看"), a("我讀到「海很藍」,還有「不是原文」。", "buffalo", spans)]);
  };
  it("spans 裡的「」是按鈕;不在 spans 裡的「」照一般文字", async () => {
    withQuote([{ quote: "海很藍", start: 0, end: 3 }]);
    mount();
    expect(await (await findLog()).findByRole("button", { name: "「海很藍」" })).toBeTruthy();
    expect(log().queryByRole("button", { name: "「不是原文」" })).toBeNull();
    expect(log().getByText(/「不是原文」/)).toBeTruthy();
  });
  it("滑過 → 稿上那道痕跡亮;點 → 稿上那段閃一下", async () => {
    withQuote([{ quote: "海很藍", start: 0, end: 3 }]);
    const { container } = mount();
    const iq = await (await findLog()).findByRole("button", { name: "「海很藍」" });
    const mark = container.querySelector(".dash-mark")!;
    expect(mark.textContent).toBe("海很藍");
    fireEvent.mouseEnter(iq);
    expect(mark.classList.contains("is-hover")).toBe(true);
    fireEvent.mouseLeave(iq);
    expect(mark.classList.contains("is-hover")).toBe(false);
    fireEvent.click(iq);
    expect(container.querySelector(".paper-sheet p")!.classList.contains("is-flash")).toBe(true);
  });
  it("點稿上的痕跡 → 右欄切回對話並閃那則訊息", async () => {
    withQuote([{ quote: "海很藍", start: 0, end: 3 }]);
    const { container } = mount();
    await (await findLog()).findByRole("button", { name: "「海很藍」" });
    fireEvent.click(screen.getByRole("tab", { name: "筆記" }));
    expect(screen.getByRole("tab", { name: "對話" }).getAttribute("aria-selected")).toBe("false");
    fireEvent.click(container.querySelector(".dash-mark")!);
    expect(screen.getByRole("tab", { name: "對話" }).getAttribute("aria-selected")).toBe("true");
    expect(container.querySelector(".chat-turn.is-flash")!.textContent).toContain("海很藍");
  });
  it("看舊版:局與結構資料都抓那一版;這版對不到的引文是灰的、有說明,稿上不畫", async () => {
    versions = [1, 2];
    withQuote([{ quote: "海很藍", start: null, end: null }]);
    const { container } = mount("/w/d1?v=1");
    const iq = await (await findLog()).findByRole("button", { name: "「海很藍」" });
    expect(iq.getAttribute("title")).toBe("這句在第 1 版找不到");
    expect(iq.classList.contains("is-lost")).toBe(true);
    expect(calls()).toContain("/api/sessions/s1?v=1");
    expect(calls()).toContain("/api/works/d1/map?v=1");
    expect(container.querySelector(".dash-mark")).toBeNull();
  });
  it("看舊版時送出:message 之後以 ?v= 重抓該局,不把最新版的位置畫到舊稿上", async () => {
    versions = [1, 2];
    withQuote([]);
    talkReply = reply("「海很藍」", "buffalo", "s1", [{ quote: "海很藍", start: 0, end: 3 }]);
    const { container } = mount("/w/d1?v=1");
    await (await findLog()).findByText(/不是原文/);
    const before = calls().filter(c => c === "/api/sessions/s1?v=1").length;
    say("再看");
    await waitFor(() => expect(calls().filter(c => c === "/api/sessions/s1?v=1").length).toBeGreaterThan(before));
    expect(container.querySelector(".dash-mark")).toBeNull();
  });
});

describe("對話錯誤與上限", () => {
  beforeEach(() => localStorage.setItem("hyenovel.companion", "buffalo"));
  it("串流中的 error 事件用它帶的 code 顯示", async () => {
    talkReply = () => sse(["error", { where: "discuss", message: "用量已達上限", recoverable: true, code: "usage-limit" }]);
    mount();
    await screen.findByText("第一段。");
    say("嗨");
    expect((await screen.findByRole("alert")).textContent).toContain("現在重試也沒用");
  });
  it("error 事件沒帶 code 時退回通用訊息", async () => {
    talkReply = () => sse(["error", { where: "discuss", message: "x", recoverable: false }]);
    mount();
    await screen.findByText("第一段。");
    say("嗨");
    expect((await screen.findByRole("alert")).textContent).toBe("出了點狀況,請再試一次。");
  });
  it("輸入框有 maxLength,與 den 的訊息上限一致", async () => {
    mount();
    expect((await screen.findByLabelText("對話輸入") as HTMLTextAreaElement).maxLength).toBe(8000);
  });
  it("送出一輪後作品清單重抓(updated_at 才會更新)", async () => {
    mount();
    await screen.findByText("第一段。");
    const recent = () => calls().filter(c => c === "/api/works").length;
    const before = recent();
    say("嗨");
    await waitFor(() => expect(recent()).toBeGreaterThan(before));
  });
});

describe("沒有寫死角色", () => {
  it("dash 目錄除 Avatar 外沒有 hyena/buffalo/deer 字面值", () => {
    const dir = join(__dirname, "../src/dash");
    for (const f of readdirSync(dir)) {
      if (f === "Avatar.tsx" || !/\.(tsx?|css)$/.test(f)) continue;
      expect(readFileSync(join(dir, f), "utf8"), f).not.toMatch(/hyena|buffalo|deer/);
    }
  });
});

describe("邊說邊畫線", () => {
  beforeEach(() => { text = "海很藍。第二句。"; localStorage.setItem("hyenovel.companion", "buffalo"); });
  afterEach(() => { delete (window as { matchMedia?: unknown }).matchMedia; });
  /** 先送 tokens,等 release() 才送 message(帶 spans)。 */
  const gated = (tokens: string[], spans: Span[], before?: () => void) => {
    let release!: () => void;
    const gate = new Promise<void>(r => { release = r; });
    const full = tokens.join("");
    talkReply = () => new Response(new ReadableStream({
      async start(c) {
        const enc = new TextEncoder();
        const w = (event: string, data: unknown) => c.enqueue(enc.encode(`data: ${JSON.stringify({ event, data })}\n\n`));
        for (const t of tokens) w("token", { text: t });
        await gate;
        before?.();
        w("message", { role: "assistant", text: full, session_id: "s1", mode: "direct", character: "buffalo", spans });
        w("done", { ok: true, session_id: "s1" });
        c.close();
      },
    }));
    return () => release();
  };
  const markEls = (c: HTMLElement) => [...c.querySelectorAll<HTMLElement>(".dash-mark")];
  const reduce = () => {
    window.matchMedia = ((q: string) => ({ matches: q.includes("reduce"), media: q, addEventListener() {}, removeEventListener() {} })) as unknown as typeof window.matchMedia;
  };

  it("串流中引文一收尾、稿上逐字找得到 → message 前就畫上(is-drawing);message 後同一段不出現第二個", async () => {
    const release = gated(["我讀到「海", "很藍」,"], [{ quote: "海很藍", start: 0, end: 3 }]);
    const { container } = mount();
    await screen.findByText("海很藍。第二句。");
    say("看看");
    await waitFor(() => expect(markEls(container)).toHaveLength(1));
    const m = markEls(container)[0];
    expect(m.textContent).toBe("海很藍");
    expect(m.classList.contains("is-drawing")).toBe(true);
    expect(log().queryByRole("button", { name: "「海很藍」" })).toBeNull();   // 還沒到 message
    release();
    await (await findLog()).findByRole("button", { name: "「海很藍」" });
    expect(markEls(container)).toHaveLength(1);
    expect(markEls(container)[0]).toBe(m);   // 同一個元素,沒有重掛載重畫
  });
  it("引文只差標點(逐字找不到)→ message 前沒有;message 帶 spans 後補畫", async () => {
    const release = gated(["「海很藍,第二句」"], [{ quote: "海很藍,第二句", start: 0, end: 7 }]);
    const { container } = mount();
    await screen.findByText("海很藍。第二句。");
    say("看看");
    await screen.findByText("「海很藍,第二句」");
    expect(markEls(container)).toHaveLength(0);
    release();
    await waitFor(() => expect(markEls(container)).toHaveLength(1));
    expect(markEls(container)[0].textContent).toBe("海很藍。第二句");
    expect(markEls(container)[0].classList.contains("is-drawing")).toBe(true);
  });
  it("多段排隊:一次畫一筆,前一筆畫完(停留 = 筆畫動畫長度,至少 600ms)才換下一筆", async () => {
    gated(["「海很藍」和「第二句」"], []);
    const { container } = mount();
    await screen.findByText("海很藍。第二句。");
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {});
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {});
    vi.useFakeTimers();
    const flush = async (until: () => boolean) => {
      for (let i = 0; i < 300 && !until(); i++) await act(async () => { await Promise.resolve(); });
    };
    say("看看");
    await flush(() => markEls(container).length === 2);
    const drawing = () => markEls(container).map(m => m.classList.contains("is-drawing"));
    expect(drawing()).toEqual([true, false]);
    // 佇列每筆停留 = 筆畫動畫長度(同一個常數):畫到一半不換下一筆
    expect(markEls(container)[0].style.getPropertyValue("--dash-draw")).toBe(`${DRAW_MS}ms`);
    act(() => { vi.advanceTimersByTime(DRAW_MS - 1); });
    expect(drawing()).toEqual([true, false]);
    act(() => { vi.advanceTimersByTime(1); });
    expect(drawing()).toEqual([false, true]);
    act(() => { vi.advanceTimersByTime(DRAW_MS); });
    expect(drawing()).toEqual([false, false]);
  });
  it("減動:痕跡直接到終態,沒有 is-drawing", async () => {
    reduce();
    const release = gated(["「海很藍」"], [{ quote: "海很藍", start: 0, end: 3 }]);
    const { container } = mount();
    await screen.findByText("海很藍。第二句。");
    say("看看");
    await waitFor(() => expect(markEls(container)).toHaveLength(1));
    expect(container.querySelector(".is-drawing")).toBeNull();
    release();
    await (await findLog()).findByRole("button", { name: "「海很藍」" });
    expect(container.querySelector(".is-drawing")).toBeNull();
  });
  it("看舊版:串流中不畫;message 後以 ?v= 重抓這局,依回來的 spans 直接畫上(不播動畫)", async () => {
    versions = [1, 2];
    rows = [row("s1")];
    session("s1", [u("先前"), a("嗯", "buffalo")]);
    const release = gated(["「海很藍」"], [{ quote: "海很藍", start: 4, end: 7 }], () => {
      session("s1", [u("先前"), a("嗯", "buffalo"), u("看看"), a("「海很藍」", "buffalo", [{ quote: "海很藍", start: 0, end: 3 }])]);
    });
    const { container } = mount("/w/d1?v=1");
    await (await findLog()).findByText("嗯");
    const before = calls().filter(c => c === "/api/sessions/s1?v=1").length;
    say("看看");
    await screen.findByText("「海很藍」");
    expect(markEls(container)).toHaveLength(0);
    release();
    await waitFor(() => expect(calls().filter(c => c === "/api/sessions/s1?v=1").length).toBeGreaterThan(before));
    await waitFor(() => expect(markEls(container)).toHaveLength(1));
    expect(markEls(container)[0].textContent).toBe("海很藍");
    expect(markEls(container)[0].classList.contains("is-drawing")).toBe(false);
  });
});
