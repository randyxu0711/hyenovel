import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import Dash from "../src/dash/Dash";
import { setLang } from "../src/dash/i18n";
import { olive, hyena, buffalo, deer } from "./dash-fixtures";

let serverDefault = "hyena";

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
const W = (slug: string, title: string, updated_at: number, state = "ready", version = 1) =>
  ({ slug, title, version, chars: 4, updated_at, state });
let works: object[];
let sessionRows: object[];
let calls: { url: string; body?: any }[];
let worksFetch: (() => Promise<Response>) | null;

function Where() { const l = useLocation(); return <output data-testid="loc">{l.pathname}{l.search}</output>; }
let recent: object[];
let chat: Record<string, object>;
const sse = (...evs: [string, unknown][]) => new Response(new ReadableStream({
  start(c) {
    const enc = new TextEncoder();
    for (const [event, data] of evs) c.enqueue(enc.encode(`data: ${JSON.stringify({ event, data })}\n\n`));
    c.close();
  },
}));
function mount(path = "/") {
  const f = vi.fn(async (u: string, init?: RequestInit) => {
    calls.push({ url: u, body: init?.body && typeof init.body === "string" ? JSON.parse(init.body) : undefined });
    if (u === "/api/themes") return json({ themes: [olive], default: "olive" });
    if (u === "/api/characters") return json({ characters: [hyena, buffalo, deer], default: serverDefault });
    if (u === "/api/works") return worksFetch ? worksFetch() : json({ works });
    if (u === "/api/estimate?chars=2001") return json({ estimate: { seconds: 300, output_tokens: 1, basis: 2 } });
    if (u === "/api/extract") return json({ filename: "海.md", text: "檔案內容", chars: 4 });
    if (u === "/api/stories") return json({ slug: "d9", title: "海", version: 1, new_version: true, reused: false });
    if (u === "/api/jobs") return json({ job_id: 5 });
    if (u.endsWith("/sessions")) return json({ sessions: sessionRows });
    if (u.startsWith("/api/sessions?")) return json({ sessions: recent });
    if (u === "/api/discuss") return sse(["message", { role: "assistant", text: "嗨,你好", session_id: "c1", seq: 1, character: "hyena", spans: [], v: null, attachment: null }],
      ["done", { ok: true, session_id: "c1" }]);
    if (u.startsWith("/api/sessions/")) return json(chat[decodeURIComponent(u.split("/").pop()!)] ?? {});
    if (u.startsWith("/api/works/")) return json({ slug: "d2", title: "海", version: 1, text: "內文一行", state: "ready", job_id: null, notes_ready: false, versions: [1] });
    return json({});
  });
  vi.stubGlobal("fetch", f);
  const tree = (
    <MemoryRouter initialEntries={[path]}>
      <Where />
      <Routes>
        <Route path="/" element={<Dash />} />
        <Route path="/c/:session" element={<Dash />} />
        <Route path="/w/:slug" element={<Dash />} />
      </Routes>
    </MemoryRouter>
  );
  render(tree);
}
const box = () => screen.findByRole("textbox", { name: "對話輸入" });
const confirmBtn = () => screen.queryByRole("button", { name: "分析" });

beforeEach(() => {
  setLang("zh-Hant"); localStorage.clear(); serverDefault = "hyena"; calls = [];
  works = [W("d2", "海", 200), W("d1", "山", 100)]; sessionRows = []; worksFetch = null; recent = []; chat = {};
});
afterEach(() => vi.unstubAllGlobals());

describe("進門只有一欄聊天", () => {
  it("只有一個輸入框、只有一隻讀伴,沒有交稿紙", async () => {
    mount();
    await box();
    await waitFor(() => expect(calls.some(c => c.url === "/api/works")).toBe(true));
    expect(document.querySelectorAll(".home textarea").length).toBe(1);
    expect(document.querySelectorAll(".home svg.fig").length).toBe(1);
    expect(document.querySelector(".home-inner")).toBeNull();
    expect(calls.some(c => c.url.endsWith("/sessions"))).toBe(false);
  });
  it("輸入框上的角色是預設讀伴,placeholder 說可以貼稿", async () => {
    serverDefault = "deer";
    mount();
    const b = await box();
    await waitFor(() => expect(document.querySelector(".home svg.fig")!.getAttribute("data-who")).toBe("deer"));
    await waitFor(() => expect(b.getAttribute("placeholder")).toMatch(/貼上一篇稿/));
  });
  it("打很長的字按 Enter → 交稿確認條,不送聊天;短字按 Enter 照常聊天;組字中不觸發", async () => {
    mount();
    const b = await box();
    fireEvent.change(b, { target: { value: "字".repeat(2001) } });
    fireEvent.keyDown(b, { key: "Enter", isComposing: true });
    expect(confirmBtn()).toBeNull();
    fireEvent.keyDown(b, { key: "Enter" });
    expect(await screen.findByText("2001 字")).toBeTruthy();
    expect(confirmBtn()).not.toBeNull();
    expect(calls.some(c => c.url === "/api/discuss")).toBe(false);
    fireEvent.change(b, { target: { value: "短短五個字" } });
    fireEvent.keyDown(b, { key: "Enter" });
    await waitFor(() => expect(calls.find(c => c.url === "/api/discuss")?.body).toMatchObject({ message: "短短五個字" }));
  });
  it("交新稿:從作品頁回到 / 並把游標放進輸入框", async () => {
    localStorage.setItem("hyenovel.shelf", "open");
    mount();
    fireEvent.click(within(await screen.findByRole("navigation")).getByRole("button", { name: /^海/ }));
    await screen.findByText("內文一行");
    fireEvent.click(screen.getByRole("button", { name: "開一局聊天" }));
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/"));
    const b = await box();
    await waitFor(() => expect(document.activeElement).toBe(b));
  });
});

describe("沒有作品", () => {
  beforeEach(() => { works = []; });
  it("拖 .md 檔:輸入框上方出現字數與「分析」確認鈕,確認後打 /api/stories 並導到新作品", async () => {
    mount();
    await box();
    const home = document.querySelector(".home")!;
    fireEvent.drop(home, { dataTransfer: { files: [new File(["x"], "海.md")] } });
    expect(await screen.findByText("4 字")).toBeTruthy();
    expect(screen.queryByText(/預估/)).toBeNull();
    expect(screen.getByText("會花額度")).toBeTruthy();
    expect(document.querySelector(".chat-att")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "分析" }));
    await waitFor(() => expect(calls.some(c => c.url === "/api/stories")).toBe(true));
    expect(calls.find(c => c.url === "/api/stories")!.body).toMatchObject({ text: "檔案內容", title: "海" });
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/w/d9"));
  });
  it("拖到對話區上也是交稿確認,不是附件", async () => {
    mount();
    await box();
    fireEvent.drop(document.querySelector(".home .chat")!, { dataTransfer: { files: [new File(["x"], "海.md")] } });
    expect(await screen.findByText("4 字")).toBeTruthy();
    expect(calls.some(c => c.url.includes("/attach"))).toBe(false);
  });
  it("貼上 > 2000 字進交稿確認,不進輸入框;短文字照常留在輸入框", async () => {
    mount();
    const b = await box() as HTMLTextAreaElement;
    fireEvent.paste(b, { clipboardData: { getData: () => "短短的" } });
    expect(confirmBtn()).toBeNull();
    fireEvent.paste(b, { clipboardData: { getData: () => "字".repeat(2001) } });
    expect(await screen.findByText("2001 字")).toBeTruthy();
    expect(await screen.findByText("約 5 分")).toBeTruthy();
    expect(b.value).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() => expect(confirmBtn()).toBeNull());
    expect(await box()).toBeTruthy();
  });
});

describe("作品清單還沒到 / 抓不到", () => {
  it("載入中:說載入中", async () => {
    worksFetch = () => new Promise<Response>(() => {});
    mount();
    await box();
    expect(screen.getByText("載入中……")).toBeTruthy();
  });
  it("抓失敗:顯示錯誤", async () => {
    worksFetch = async () => { throw new TypeError("down"); };
    mount();
    expect(await screen.findByText("連不上本機的 den,請確認它有在跑。")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toBe("連不上本機的 den,請確認它有在跑。");
  });
});


const free = (session: string, preview: string) =>
  ({ session, slug: null, title: null, started_at: 1, last_at: 2, turns: 1, character: "hyena", preview, legacy: false });
const detail = (session: string, over: object = {}) => ({ session, slug: null, title: null, legacy: false, version: null, attachments: [],
  turns: [{ seq: 0, role: "assistant", text: `${session} 的話`, ts: 1, character: "hyena", quotes: [], spans: [], v: null }], ...over });

describe("進門聊天", () => {
  it("home first turn moves url to /c/:session", async () => {
    localStorage.setItem("hyenovel.shelf", "open");
    mount();
    const talk = within(await screen.findByRole("region", { name: "對話" }));
    fireEvent.change(talk.getByLabelText("對話輸入"), { target: { value: "隨便聊聊" } });
    fireEvent.click(talk.getByRole("button", { name: "送出" }));
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/c/c1"));
    expect(calls.find(c => c.url === "/api/discuss")!.body).toMatchObject({ session_id: null, message: "隨便聊聊" });
    expect(await talk.findByText("嗨,你好")).toBeTruthy();
  });

  it("shelf lists storyless sessions under chat group", async () => {
    localStorage.setItem("hyenovel.shelf", "open");
    recent = [free("c1", "聊海"), { ...free("w1", "作品局"), slug: "d2", title: "海" }];
    chat = { c1: detail("c1") };
    mount();
    const group = within(await screen.findByRole("region", { name: "聊天" }));
    fireEvent.click(await group.findByRole("button", { name: /聊海/ }));
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/c/c1"));
    expect(group.queryByRole("button", { name: /作品局/ })).toBeNull();
    expect(await screen.findByText("c1 的話")).toBeTruthy();
  });

  it("plus on chat group opens empty chat", async () => {
    localStorage.setItem("hyenovel.shelf", "open");
    chat = { c1: detail("c1") };
    mount("/c/c1");
    expect(await screen.findByText("c1 的話")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "開一局聊天" }));
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/"));
    await waitFor(() => expect(screen.queryByText("c1 的話")).toBeNull());
  });

  it("chat + on a work page goes to an empty home chat and stays there", async () => {
    localStorage.setItem("hyenovel.shelf", "open");
    sessionRows = [{ session: "w1", started_at: 1, last_at: 2, turns: 1, character: "hyena", preview: "進度如何", legacy: false }];
    chat = { w1: { ...detail("w1"), slug: "d2", title: "海", version: 1 } };
    mount("/w/d2?s=w1");
    await screen.findByText("w1 的話");
    fireEvent.click(within(screen.getByRole("region", { name: "聊天" })).getByRole("button", { name: "開一局聊天" }));
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/"));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText("對話輸入")));
    await new Promise(r => setTimeout(r, 50));
    expect(screen.getByTestId("loc").textContent).toBe("/");
    expect(screen.queryByText("w1 的話")).toBeNull();
  });

  it("brand goes home from a work page", async () => {
    localStorage.setItem("hyenovel.shelf", "open");
    mount("/w/d2");
    await screen.findByText("內文一行");
    fireEvent.click(screen.getByRole("link", { name: /Hyenovel/ }));
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/"));
  });

  it("archiving the open chat from the shelf drops the row and starts a fresh chat", async () => {
    localStorage.setItem("hyenovel.shelf", "open");
    recent = [free("c1", "聊海")];
    chat = { c1: detail("c1") };
    mount("/c/c1");
    await screen.findByText("c1 的話");
    const group = within(screen.getByRole("region", { name: "聊天" }));
    await group.findByText("聊海");
    fireEvent.click(group.getByRole("button", { name: "封存這局" }));
    await waitFor(() => expect(group.queryByText("聊海")).toBeNull());
    expect(calls.some(c => c.url === "/api/sessions/c1/archive")).toBe(true);
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/"));
    expect(screen.queryByText("c1 的話")).toBeNull();
  });

  it("a chat that became a work opens on the work page", async () => {
    chat = { c1: detail("c1", { slug: "d2", title: "海", version: 1 }) };
    mount("/c/c1");
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/w/d2?s=c1"));
  });
});
