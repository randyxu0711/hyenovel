import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within, act } from "@testing-library/react";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Dash from "../src/dash/Dash";
import { setLang } from "../src/dash/i18n";
import { olive, hyena, buffalo, deer } from "./dash-fixtures";

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
const sse = (...evs: [string, unknown][]) => new Response(new ReadableStream({
  start(c) {
    const enc = new TextEncoder();
    for (const [event, data] of evs) c.enqueue(enc.encode(`data: ${JSON.stringify({ event, data })}\n\n`));
    c.close();
  },
}));
const works = [{ slug: "d1", title: "海", version: 1, chars: 4 }];
let talkBodies: any[];
let talkReply: () => Response;
let sessions: Record<string, object>;

function mount(chars = [hyena, buffalo, deer]) {
  const f = vi.fn(async (u: string, init?: RequestInit) => {
    if (u === "/api/themes") return json({ themes: [olive], default: "olive" });
    if (u === "/api/characters") return json({ characters: chars, default: "hyena" });
    if (u === "/api/works") return json({ works });
    if (u === "/api/works/d1") return json({ slug: "d1", title: "海", version: 1, text: "第一段。", state: "ready", job_id: null, notes_ready: false });
    if (u.startsWith("/api/discuss/")) { talkBodies.push(JSON.parse(String(init?.body))); return talkReply(); }
    if (u.startsWith("/api/sessions/")) return json(sessions[decodeURIComponent(u.split("/").pop()!)]);
    if (u.startsWith("/api/sessions?")) return json({ sessions: Object.keys(sessions).map(k => ({ session: k, slug: "d1", title: "海", started_at: 1, last_at: 2, turns: 4, character: null, mode: null, preview: "q1", version: 1 })) });
    return json({ sessions: [] });
  });
  vi.stubGlobal("fetch", f);
  return render(<MemoryRouter initialEntries={["/w/d1"]}><Routes><Route path="/w/:slug" element={<Dash />} /></Routes></MemoryRouter>);
}
const reply = (text: string, character = "hyena", sid = "s1") => () => sse(
  ["token", { text: text.slice(0, 1) }], ["token", { text: text.slice(1) }],
  ["message", { role: "assistant", text, session_id: sid, mode: "slow", character }], ["done", { ok: true, session_id: sid }]);
const say = (s: string) => {
  fireEvent.change(screen.getByLabelText("對話輸入"), { target: { value: s } });
  fireEvent.click(screen.getByRole("button", { name: "送出" }));
};

beforeEach(() => { setLang("zh-Hant"); localStorage.clear(); talkBodies = []; talkReply = reply("嗯"); sessions = {}; });
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("選人", () => {
  it("在名冊上選過的角色會被記住", async () => {
    const { unmount } = mount();
    const pick = async () => screen.findByRole("button", { name: "水牛" });
    fireEvent.click(await pick());
    expect((await pick()).getAttribute("aria-pressed")).toBe("true");
    unmount();
    mount();
    expect((await pick()).getAttribute("aria-pressed")).toBe("true");
  });
  // TODO(Task 12): 作品頁要能打開既有的局(舊的左欄「對話」清單已移除)
  it.todo("沒選過人時打開既有的局:直接看逐字,接著由最後說話的那位陪讀");
  it("記住的角色不在清單時退回預設", async () => {
    localStorage.setItem("hyenovel.companion", "ghost");
    mount();
    await screen.findByLabelText("對話輸入");
    say("嗨");
    await waitFor(() => expect(talkBodies[0].character).toBe("hyena"));
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
    fireEvent.click(await screen.findByRole("button", { name: "帶給水牛聊" }));
    say("這段怎麼樣");
    await screen.findByText("嗯");
    expect(talkBodies[0]).toMatchObject({ character: "buffalo", quotes: ["第一段"], message: "這段怎麼樣", session_id: null });
    const log = screen.getByRole("log");
    expect(within(log).getByText("第一段")).toBeTruthy();
    expect(within(log).getByText("這段怎麼樣")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "拿掉這段引文" })).toBeNull();
  });
  it("token 逐段接上、沒有計時器;message 到了換成正式訊息並標說話者", async () => {
    let release!: () => void;
    const gate = new Promise<void>(r => { release = r; });
    talkReply = () => new Response(new ReadableStream({
      async start(c) {
        const enc = new TextEncoder();
        const w = (event: string, data: unknown) => c.enqueue(enc.encode(`data: ${JSON.stringify({ event, data })}\n\n`));
        w("token", { text: "半" });
        await gate;
        w("token", { text: "句" });
        w("message", { role: "assistant", text: "半句", session_id: "s1", mode: "direct", character: "buffalo" });
        w("done", { ok: true, session_id: "s1" });
        c.close();
      },
    }));
    mount();
    await screen.findByText("第一段。");
    vi.useFakeTimers();
    const flush = async (until: () => boolean) => {
      for (let i = 0; i < 200 && !until(); i++) await act(async () => { await Promise.resolve(); });
    };
    say("嗨");
    await flush(() => !!screen.queryByText("半"));
    expect(screen.getByText("半")).toBeTruthy();
    expect(vi.getTimerCount()).toBe(0);   // 串流中沒有任何排程計時器
    release();
    await flush(() => !!screen.queryByText("半句"));
    expect(within(screen.getByRole("log")).getByText("半句")).toBeTruthy();
    expect(within(screen.getByRole("log")).getByText("水牛")).toBeTruthy();
    expect(vi.getTimerCount()).toBe(0);
  });
  // TODO(Task 12): 同上,需要作品頁能打開既有的局
  it.todo("說話者換人時有分隔線;舊局沒有 character 時用同 mode 的角色標示");
  it("409 busy 顯示訊息且輸入框保留原字", async () => {
    talkReply = () => json({ detail: "busy", code: "busy" }, 409);
    mount();
    await screen.findByText("第一段。");
    say("還沒說完的話");
    expect((await screen.findByRole("alert")).textContent).toBe("這一局還有一輪在進行,稍等一下。");
    expect((screen.getByLabelText("對話輸入") as HTMLTextAreaElement).value).toBe("還沒說完的話");
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
    const f = fetch as unknown as ReturnType<typeof vi.fn>;
    await screen.findByText("第一段。");
    const recent = () => f.mock.calls.filter(c => c[0] === "/api/works").length;
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
