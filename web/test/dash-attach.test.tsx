import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useLocation, useParams } from "react-router-dom";
import { setLang } from "../src/dash/i18n";
import { LinksProvider } from "../src/dash/links";
import Talk from "../src/dash/Talk";
import { CharactersProvider, makeCharacters } from "../src/dash/useCharacters";
import { useTalk } from "../src/dash/useTalk";
import { hyena, buffalo, deer } from "./dash-fixtures";

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
const sse = (...evs: [string, unknown][]) => new Response(new ReadableStream({
  start(c) {
    const enc = new TextEncoder();
    for (const [event, data] of evs) c.enqueue(enc.encode(`data: ${JSON.stringify({ event, data })}\n\n`));
    c.close();
  },
}));
const a = (seq: number, t: string) => ({ seq, role: "assistant", text: t, ts: 1, character: "hyena", quotes: [], spans: [], v: null });
const u = (seq: number, t: string) => ({ seq, role: "user", text: t, ts: 1, character: null, quotes: [], spans: [], v: null });

let detail: Record<string, unknown>;
let bodies: any[];
let posts: string[];

function Host() {
  const { session } = useParams();
  const talk = useTalk(null, undefined, null, session ?? null);
  return <Talk talk={talk} version={1} quotes={[]} analyzing={false} onDropQuote={() => {}} onSent={() => {}} onReveal={() => {}} />;
}
function Where() { const l = useLocation(); return <output data-testid="loc">{l.pathname}{l.search}</output>; }

function mount(path = "/c/c1") {
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const p = url.split("?")[0];
    if (init?.method === "POST") posts.push(p);
    if (p === "/api/discuss") {
      bodies.push(JSON.parse(String(init?.body)));
      return sse(["token", { text: "讀" }],
        ["message", { role: "assistant", text: "讀了", session_id: "c1", seq: 1, character: "hyena", spans: [], v: null, attachment: 1 }],
        ["done", { ok: true, session_id: "c1" }]);
    }
    if (p === "/api/sessions/c1/attachments/1/adopt") return json({ slug: "d9", title: "海", version: 1, reused: false }, 201);
    if (p === "/api/sessions/c1/compact") return json({ seq: 9, text: "摘要文字" }, 201);
    if (p === "/api/sessions/c1/clear") return json({ seq: 9 }, 201);
    if (p === "/api/sessions/c1") return json(detail);
    return json({});
  }));
  return render(
    <MemoryRouter initialEntries={[path]}>
      <CharactersProvider value={makeCharacters([hyena, buffalo, deer], "hyena")}>
        <LinksProvider>
          <Where />
          <Routes>
            <Route path="/c/:session" element={<Host />} />
            <Route path="/" element={<Host />} />
            <Route path="/w/:slug" element={<p>work</p>} />
          </Routes>
        </LinksProvider>
      </CharactersProvider>
    </MemoryRouter>);
}

const file = (name: string, text: string) => Object.assign(new File([text], name, { type: "text/plain" }), { text: async () => text });

beforeEach(() => {
  setLang("zh-Hant"); localStorage.clear(); bodies = []; posts = [];
  detail = { session: "c1", slug: null, title: null, legacy: false, version: null, turns: [u(0, "嗨"), a(1, "你好")], attachments: [] };
});
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("純聊天的附件", () => {
  it("attach sends file text with next turn and shows card", async () => {
    mount("/");
    const input = await screen.findByLabelText("丟一份稿進來", { selector: "input" });
    fireEvent.change(input, { target: { files: [file("海.md", "浪打上來。")] } });
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ session_id: null, message: "", attach: { name: "海", text: "浪打上來。" } });
    expect(await screen.findByText("海")).toBeTruthy();
    expect(screen.getByText("5 字")).toBeTruthy();
    expect(screen.getByRole("button", { name: "開成作品" })).toBeTruthy();
  });

  it("drafted text waits: the file goes with the next send", async () => {
    mount("/");
    fireEvent.change(await screen.findByLabelText("對話輸入"), { target: { value: "看這篇" } });
    fireEvent.change(screen.getByLabelText("丟一份稿進來", { selector: "input" }), { target: { files: [file("山.txt", "石頭")] } });
    await screen.findByRole("button", { name: "不帶這份稿" });
    expect(bodies).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "送出" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ message: "看這篇", attach: { name: "山", text: "石頭" } });
  });

  it("only .md / .txt are taken", async () => {
    mount("/");
    fireEvent.change(await screen.findByLabelText("丟一份稿進來", { selector: "input" }), { target: { files: [file("a.pdf", "x")] } });
    await new Promise(r => setTimeout(r, 10));
    expect(bodies).toHaveLength(0);
  });

  it("adopt on unbound session navigates to work", async () => {
    detail = { ...detail, attachments: [{ n: 1, seq: 0, name: "海", chars: 5, adopted: false }] };
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "開成作品" }));
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/w/d9?s=c1"));
    expect(posts).toContain("/api/sessions/c1/attachments/1/adopt");
  });

  it("bound session shows attachment card without actions", async () => {
    detail = { ...detail, slug: "d9", title: "海", version: 1, attachments: [{ n: 1, seq: 0, name: "海", chars: 5, adopted: true }] };
    mount();
    expect(await screen.findByText("海")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "開成作品" })).toBeNull();
    expect(screen.queryByLabelText("丟一份稿進來", { selector: "input" })).toBeNull();
  });

  it("compact divider renders summary collapsed", async () => {
    detail = { ...detail, turns: [...(detail.turns as object[]), { seq: 2, role: "compact", text: "之前聊了海", ts: 2 }, { seq: 3, role: "clear", ts: 3 }] };
    mount();
    const sum = await screen.findByText("之前聊了海");
    expect(sum.closest("details")!.hasAttribute("open")).toBe(false);
    expect(screen.getByRole("separator", { name: "對話清空" })).toBeTruthy();
  });

  it("clear and compact buttons post and add a divider", async () => {
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "壓縮對話" }));
    expect(await screen.findByText("摘要文字")).toBeTruthy();
    expect(screen.getByRole("button", { name: "壓縮對話" }).getAttribute("title")).toContain("額度");
    fireEvent.click(screen.getByRole("button", { name: "清空對話" }));
    await screen.findByRole("separator", { name: "對話清空" });
    expect(posts).toEqual(["/api/sessions/c1/compact", "/api/sessions/c1/clear"]);
  });

  it("typing / lists commands; /clear + Enter clears instead of sending", async () => {
    mount();
    await screen.findByText("嗨");
    const box = screen.getByLabelText("對話輸入");
    fireEvent.change(box, { target: { value: "/" } });
    const menu = screen.getByRole("listbox", { name: "指令" });
    expect(within(menu).getAllByRole("option").map(o => o.textContent)).toEqual(["/clear清空對話", "/compact壓縮對話(花一次額度)"]);
    fireEvent.change(box, { target: { value: "/cl" } });
    expect(within(screen.getByRole("listbox", { name: "指令" })).getAllByRole("option")).toHaveLength(1);
    fireEvent.keyDown(box, { key: "Enter" });
    expect((box as HTMLTextAreaElement).value).toBe("/clear");
    expect(posts).toEqual([]);
    fireEvent.keyDown(box, { key: "Enter" });
    await screen.findByRole("separator", { name: "對話清空" });
    expect(posts).toEqual(["/api/sessions/c1/clear"]);
    expect((box as HTMLTextAreaElement).value).toBe("");
    expect(screen.queryByRole("listbox", { name: "指令" })).toBeNull();
  });

  it("a prefix never spends: /co + Enter only completes to /compact", async () => {
    mount();
    await screen.findByText("嗨");
    const box = screen.getByLabelText("對話輸入");
    fireEvent.change(box, { target: { value: "/co" } });
    fireEvent.keyDown(box, { key: "Enter" });
    fireEvent.change(box, { target: { value: "/" } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect((box as HTMLTextAreaElement).value).toBe("/clear");
    await new Promise(r => setTimeout(r, 20));
    expect(posts).toEqual([]);
  });

  it("slash menu: arrows pick, Esc closes, unknown command is sent as text", async () => {
    mount();
    await screen.findByText("嗨");
    const box = screen.getByLabelText("對話輸入");
    fireEvent.change(box, { target: { value: "/" } });
    fireEvent.keyDown(box, { key: "ArrowDown" });
    const opts = within(screen.getByRole("listbox", { name: "指令" })).getAllByRole("option");
    expect(opts[1].getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(box, { key: "Escape" });
    expect(screen.queryByRole("listbox", { name: "指令" })).toBeNull();
    fireEvent.change(box, { target: { value: "/海 是什麼" } });
    expect(screen.queryByRole("listbox", { name: "指令" })).toBeNull();
  });

  it("remember on storyless session hides work scope", async () => {
    mount();
    const me = await screen.findByText("嗨");
    fireEvent.click(within(me.closest(".chat-me") as HTMLElement).getByRole("button", { name: "記住" }));
    expect(screen.queryByRole("button", { name: "這篇" })).toBeNull();
    expect(screen.getByRole("button", { name: "每篇" }).getAttribute("aria-pressed")).toBe("true");
  });
});
