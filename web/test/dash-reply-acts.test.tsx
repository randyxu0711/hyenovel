import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
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
const held = () => {
  let close!: () => void;
  const res = new Response(new ReadableStream({ start(c) { close = () => c.close(); } }));
  return { res, close: () => close() };
};

type T = Record<string, unknown>;
const u = (seq: number, text: string): T => ({ seq, role: "user", text, ts: 1, character: null, quotes: [], spans: [] });
const a = (seq: number, text: string, over: T = {}): T =>
  ({ seq, role: "assistant", text, ts: 1, character: "hyena", quotes: [], spans: [], ...over });
const cut = (seq: number, role: "clear" | "compact"): T => ({ seq, role, text: role === "compact" ? "摘要" : "", ts: 1, character: null, quotes: [], spans: [] });

let turns: T[];
let legacy: boolean;
let regen: () => Response;
let talkReply: () => Response;
let clearReply: () => Promise<Response>;
let onPut: (url: string, body: any) => void;
let writes: { url: string; method: string; body: any }[];

function mount() {
  const f = vi.fn(async (url: string, init?: RequestInit) => {
    const p = url.split("?")[0];
    const method = init?.method ?? "GET";
    if (p === "/api/themes") return json({ themes: [olive], default: "olive" });
    if (p === "/api/characters") return json({ characters: [hyena, buffalo, deer], default: "hyena" });
    if (p === "/api/works") return json({ works: [{ slug: "d1", title: "海", version: 1, chars: 4 }] });
    if (p === "/api/works/d1") return json({ slug: "d1", title: "海", version: 1, versions: [1], text: "第一段。", state: "ready", job_id: null, notes_ready: false });
    if (p === "/api/works/d1/map") return json({ version: 1, analysis_version: null, notes_version: null, beats: [], motifs: [], notes: null });
    if (p === "/api/works/d1/sessions") return json({ sessions: [{ session: "s1", started_at: 1, last_at: 2, turns: turns.length, character: "hyena", preview: "q", version: 1, legacy }] });
    if (p.endsWith("/regenerate")) { writes.push({ url: p, method, body: null }); return regen(); }
    if (p.startsWith("/api/discuss/")) return talkReply();
    if (p === "/api/sessions/s1/clear") return clearReply();
    if (method !== "GET") {
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      writes.push({ url: p, method, body });
      onPut(p, body);
      if (p.endsWith("/text")) return json({ edited: true });
      if (p.endsWith("/variant")) return json({ variant: body.n, variants: 2 });
      return json({});
    }
    if (p === "/api/sessions/s1") return json({ session: "s1", slug: "d1", title: "海", turns, legacy, version: 1, attachments: [] });
    return json({ sessions: [] });
  });
  vi.stubGlobal("fetch", f);
  return render(<MemoryRouter initialEntries={["/w/d1?s=s1"]}>
    <Routes><Route path="/w/:slug" element={<Dash />} /></Routes></MemoryRouter>);
}
const log = async () => within(await screen.findByRole("log"));
const sessionGets = () => vi.mocked(fetch).mock.calls.filter(([u, i]: any) => u.split("?")[0] === "/api/sessions/s1" && !i?.method).length;
const last = <X,>(xs: X[]): X => xs[xs.length - 1];
const REDO = "重說(花一次額度)";

beforeEach(() => {
  setLang("zh-Hant"); localStorage.clear();
  turns = [u(0, "問"), a(1, "第一則"), u(2, "再問"), a(3, "舊的")];
  legacy = false; writes = []; onPut = () => {};
  regen = () => sse(["token", { text: "新" }], ["token", { text: "的" }],
    ["message", { role: "assistant", text: "新的", session_id: "s1", seq: 3, character: "hyena", spans: [], v: 1, attachment: null, variant: 2, variants: 2 }],
    ["done", { ok: true, session_id: "s1" }]);
  talkReply = () => sse(["done", { ok: true, session_id: "s1" }]);
  clearReply = async () => json({ seq: 4 });
});
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("重說鍵", () => {
  it("只在最後一則讀伴回覆上", async () => {
    mount();
    const l = await log();
    await l.findByText("舊的");
    const keys = l.getAllByRole("button", { name: REDO });
    expect(keys).toHaveLength(1);
    expect(keys[0].closest(".chat-turn")!.textContent).toContain("舊的");
  });

  it("後面有 clear / compact 標記就不出現", async () => {
    for (const role of ["clear", "compact"] as const) {
      turns = [u(0, "問"), a(1, "舊的"), cut(2, role)];
      const { unmount } = mount();
      const l = await log();
      await l.findByText("舊的");
      expect(l.queryByRole("button", { name: REDO })).toBeNull();
      unmount();
    }
  });

  it("舊局不可按", async () => {
    legacy = true;
    mount();
    const l = await log();
    await l.findByText("舊的");
    expect(l.getByRole("button", { name: REDO })).toBeDisabled();
  });

  it("串流中不可按", async () => {
    const h = held();
    talkReply = () => h.res;
    mount();
    const l = await log();
    await l.findByText("舊的");
    fireEvent.change(screen.getByLabelText("對話輸入"), { target: { value: "還有" } });
    fireEvent.click(screen.getByRole("button", { name: "送出" }));
    await waitFor(() => expect(l.getByRole("button", { name: REDO })).toBeDisabled());
    h.close();
  });

  it("clear 在跑(working)時不可按", async () => {
    let done!: (r: Response) => void;
    clearReply = () => new Promise(r => { done = r; });
    mount();
    const l = await log();
    await l.findByText("舊的");
    fireEvent.click(screen.getByRole("button", { name: "清空對話" }));
    await waitFor(() => expect(l.getByRole("button", { name: REDO })).toBeDisabled());
    done(json({ seq: 4 }));
  });
});

describe("重說的結果", () => {
  it("成功:同一格換字、列數不變、出現翻版器", async () => {
    mount();
    const l = await log();
    await l.findByText("舊的");
    const before = document.querySelectorAll(".chat-turn").length;
    fireEvent.click(l.getByRole("button", { name: REDO }));
    await l.findByText("新的");
    expect(l.queryByText("舊的")).toBeNull();
    expect(document.querySelectorAll(".chat-turn")).toHaveLength(before);
    expect(l.getByText("2/2")).toBeTruthy();
    expect(writes.some(w => w.url === "/api/sessions/s1/turns/3/regenerate")).toBe(true);
  });

  it("失敗:那一格回到舊字、有錯誤", async () => {
    regen = () => sse(["token", { text: "半" }], ["error", { code: "chat-failed", message: "x" }]);
    mount();
    const l = await log();
    await l.findByText("舊的");
    fireEvent.click(l.getByRole("button", { name: REDO }));
    expect(await screen.findByText("讀伴這輪沒讀成,沒有存下。稍後再試。")).toBeTruthy();
    expect(l.getByText("舊的")).toBeTruthy();
    expect(l.queryByText("半")).toBeNull();
  });
});

describe("翻版器", () => {
  it("total = 1 不出現;不是最後一則也不出現", async () => {
    turns = [u(0, "問"), a(1, "第一則", { variant: { n: 1, total: 3 } }), u(2, "再問"), a(3, "舊的", { variant: { n: 1, total: 1 } })];
    mount();
    const l = await log();
    await l.findByText("舊的");
    expect(l.queryByRole("button", { name: "上一版" })).toBeNull();
    expect(l.queryByRole("button", { name: "下一版" })).toBeNull();
  });

  it("按了呼叫挑版並重抓", async () => {
    turns = [u(0, "問"), a(1, "第二版", { variant: { n: 2, total: 2 } })];
    onPut = (url, body) => {
      if (url.endsWith("/variant")) turns = [u(0, "問"), a(1, "第一版", { variant: { n: body.n, total: 2 } })];
    };
    mount();
    const l = await log();
    await l.findByText("第二版");
    expect(l.getByText("2/2")).toBeTruthy();
    expect(l.getByRole("button", { name: "下一版" })).toBeDisabled();
    const gets = sessionGets();
    fireEvent.click(l.getByRole("button", { name: "上一版" }));
    await l.findByText("第一版");
    expect(writes).toContainEqual({ url: "/api/sessions/s1/turns/1/variant", method: "PUT", body: { n: 1 } });
    expect(sessionGets()).toBeGreaterThan(gets);
    expect(l.getByText("1/2")).toBeTruthy();
  });

  it("換版後回饋記號是那一版的", async () => {
    turns = [u(0, "問"), a(1, "第二版", { variant: { n: 2, total: 2 }, reaction: { mark: "misread", comment: null } })];
    onPut = (url, body) => {
      if (url.endsWith("/variant")) turns = [u(0, "問"), a(1, "第一版", { variant: { n: body.n, total: 2 }, reaction: null })];
    };
    mount();
    const l = await log();
    await l.findByRole("button", { name: "標記:讀錯了" });
    fireEvent.click(l.getByRole("button", { name: "上一版" }));
    await l.findByText("第一版");
    expect(l.queryByRole("button", { name: "標記:讀錯了" })).toBeNull();
    expect(l.getByRole("button", { name: "標記這則" })).toBeTruthy();
  });
});

describe("編輯", () => {
  const open = async () => {
    const l = await log();
    await l.findByText("舊的");
    const keys = l.getAllByRole("button", { name: "改這則" });
    fireEvent.click(keys[keys.length - 1]);
    return { l, box: l.getByRole("textbox", { name: "改讀伴的回覆" }) as HTMLTextAreaElement };
  };

  it("原地變文字框,內容是現有全文;Esc 取消不送", async () => {
    mount();
    const { l, box } = await open();
    expect(box.value).toBe("舊的");
    fireEvent.change(box, { target: { value: "改掉" } });
    fireEvent.keyDown(box, { key: "Escape" });
    expect(l.queryByRole("textbox", { name: "改讀伴的回覆" })).toBeNull();
    expect(l.getByText("舊的")).toBeTruthy();
    expect(writes).toEqual([]);
  });

  it("沒改就存 = 取消,不送", async () => {
    mount();
    const { l, box } = await open();
    fireEvent.keyDown(box, { key: "Enter", ctrlKey: true });
    expect(l.queryByRole("textbox", { name: "改讀伴的回覆" })).toBeNull();
    expect(writes).toEqual([]);
  });

  it("⌘Enter 存:送新字、重抓、出現「改過」", async () => {
    onPut = (url, body) => {
      if (url.endsWith("/text")) turns = [u(0, "問"), a(1, "第一則"), u(2, "再問"), a(3, body.text, { edited: true, voice: true })];
    };
    mount();
    const { l, box } = await open();
    expect(l.queryByText("改過")).toBeNull();
    fireEvent.change(box, { target: { value: "它該這樣說" } });
    fireEvent.keyDown(box, { key: "Enter", metaKey: true });
    await l.findByText("它該這樣說");
    expect(writes).toContainEqual({ url: "/api/sessions/s1/turns/3/text", method: "PUT", body: { text: "它該這樣說" } });
    expect(l.getByText("改過")).toBeTruthy();
    expect(last(l.getAllByRole("button", { name: "像它" }))).toHaveAttribute("aria-pressed", "true");
  });
});

describe("像它", () => {
  it("按下即存、再按取消;不在旗子選單裡", async () => {
    mount();
    const l = await log();
    await l.findByText("舊的");
    const key = last(l.getAllByRole("button", { name: "像它" }));
    expect(key).toHaveAttribute("title", "像它:留作它說話的樣子,之後的局會帶著");
    fireEvent.click(key);
    expect(key).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(writes).toContainEqual({ url: "/api/sessions/s1/turns/3/voice", method: "PUT", body: null }));
    fireEvent.click(key);
    expect(key).toHaveAttribute("aria-pressed", "false");
    await waitFor(() => expect(writes).toContainEqual({ url: "/api/sessions/s1/turns/3/voice", method: "DELETE", body: null }));
    const flags = l.getAllByRole("button", { name: "標記這則" });
    fireEvent.click(flags[flags.length - 1]);
    expect(within(screen.getByRole("group", { name: "標記這則" })).queryByText("像它")).toBeNull();
  });

  it("存不下就還原並顯示錯誤", async () => {
    mount();
    const l = await log();
    await l.findByText("舊的");
    vi.mocked(fetch).mockImplementationOnce(async () => json({ error: { code: "busy", message: "x" } }, 409));
    const key = last(l.getAllByRole("button", { name: "像它" }));
    fireEvent.click(key);
    await waitFor(() => expect(key).toHaveAttribute("aria-pressed", "false"));
    expect(l.getByRole("alert")).toBeTruthy();
  });
});
