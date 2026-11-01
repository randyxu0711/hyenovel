import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { StrictMode } from "react";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import Dash from "../src/dash/Dash";
import { waitingLine } from "../src/dash/Home";
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
const W = (slug: string, title: string, updated_at: number, state = "ready", version = 1) =>
  ({ slug, title, version, chars: 4, updated_at, state });
let works: object[];
let sessionRows: object[];
let calls: { url: string; body?: any }[];
let worksFetch: (() => Promise<Response>) | null;

function Where() { const l = useLocation(); return <output data-testid="loc">{l.pathname}</output>; }
function mount(strict = false) {
  const f = vi.fn(async (u: string, init?: RequestInit) => {
    calls.push({ url: u, body: init?.body && typeof init.body === "string" ? JSON.parse(init.body) : undefined });
    if (u === "/api/themes") return json({ themes: [olive], default: "olive" });
    if (u === "/api/characters") return json({ characters: [hyena, buffalo, deer], default: "hyena" });
    if (u === "/api/works") return worksFetch ? worksFetch() : json({ works });
    if (u === "/api/estimate?chars=2001") return json({ estimate: { seconds: 300, output_tokens: 1, basis: 2 } });
    if (u === "/api/extract") return json({ filename: "海.md", text: "檔案內容", chars: 4 });
    if (u === "/api/stories") return json({ slug: "d9", title: "海", version: 1, new_version: true, reused: false });
    if (u === "/api/jobs") return json({ job_id: 5 });
    if (u.startsWith("/api/discuss/"))
      return sse(["message", { role: "assistant", text: "嗯", session_id: "s1", mode: "slow", character: "hyena", spans: [] }], ["done", { ok: true }]);
    if (u.endsWith("/sessions")) return json({ sessions: sessionRows });
    if (u.startsWith("/api/works/")) return json({ slug: "d2", title: "海", version: 1, text: "內文一行", state: "ready", job_id: null, notes_ready: false, versions: [1] });
    return json({});
  });
  vi.stubGlobal("fetch", f);
  const tree = (
    <MemoryRouter initialEntries={["/"]}>
      <Where />
      <Routes>
        <Route path="/" element={<Dash />} />
        <Route path="/w/:slug" element={<Dash />} />
      </Routes>
    </MemoryRouter>
  );
  render(strict ? <StrictMode>{tree}</StrictMode> : tree);
}
const discuss = () => calls.filter(c => c.url.startsWith("/api/discuss/"));
const box = () => screen.findByRole("textbox", { name: "對話輸入" });

beforeEach(() => {
  setLang("zh-Hant"); localStorage.clear(); calls = [];
  works = [W("d2", "海", 200), W("d1", "山", 100)]; sessionRows = []; worksFetch = null;
});
afterEach(() => vi.unstubAllGlobals());

describe("waitingLine", () => {
  const ws = [W("d2", "海", 200), W("d1", "山", 100)];
  it("最近一篇讀完、最新版沒聊過 → 回它", () => expect(waitingLine(ws, { d2: [] })).toEqual({ slug: "d2", title: "海" }));
  it("最新版聊過 → null;只聊過舊版仍回它", () => {
    expect(waitingLine(ws, { d2: [1] })).toBeNull();
    expect(waitingLine([W("d2", "海", 200, "ready", 2)], { d2: [1] })).not.toBeNull();
  });
  it("狀態是 notes-running / notes-stopped 也算;running / none / stopped 不算", () => {
    for (const s of ["notes-running", "notes-stopped"]) expect(waitingLine([W("a", "x", 1, s)], {})).not.toBeNull();
    for (const s of ["running", "none", "stopped"]) expect(waitingLine([W("a", "x", 1, s)], {})).toBeNull();
  });
  it("只看最近一篇;沒有作品 → null", () => {
    expect(waitingLine([W("a", "x", 2, "running"), W("b", "y", 1)], {})).toBeNull();
    expect(waitingLine([], {})).toBeNull();
  });
});

describe("進門畫面", () => {
  it("剛讀完沒聊過:顯示《海》讀完了。與連到作品頁的「聽聽看」;只查最近那篇的局", async () => {
    mount();
    expect(await screen.findByText("《海》讀完了。")).toBeTruthy();
    expect(screen.getByRole("link", { name: /聽聽看/ }).getAttribute("href")).toBe("/w/d2");
    const asked = calls.filter(c => c.url.endsWith("/sessions")).map(c => c.url);
    expect(asked).toEqual(["/api/works/d2/sessions"]);
  });
  it("最新版已有局 → 不顯示", async () => {
    sessionRows = [{ session: "s", started_at: 1, last_at: 2, turns: 2, character: null, mode: null, preview: "", version: 1, legacy: false }];
    mount();
    await box();
    await waitFor(() => expect(calls.some(c => c.url.endsWith("/sessions"))).toBe(true));
    await new Promise(r => setTimeout(r, 20));
    expect(screen.queryByText("《海》讀完了。")).toBeNull();
  });
  it("chips 預設選最近那篇,點別篇換選", async () => {
    mount();
    const g = within(await screen.findByRole("group", { name: "聊哪一篇" }));
    expect(g.getByRole("button", { name: "海" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(g.getByRole("button", { name: "山" }));
    expect(g.getByRole("button", { name: "山" }).getAttribute("aria-pressed")).toBe("true");
    expect(g.getByRole("button", { name: "海" }).getAttribute("aria-pressed")).toBe("false");
  });
  it("送出:導到所選作品頁,該頁以新局打一次 /api/discuss", async () => {
    mount();
    fireEvent.click(within(await screen.findByRole("group", { name: "聊哪一篇" })).getByRole("button", { name: "山" }));
    fireEvent.change(await box(), { target: { value: "想聊結尾" } });
    fireEvent.click(screen.getByRole("button", { name: "送出" }));
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/w/d1"));
    await waitFor(() => expect(discuss()).toHaveLength(1));
    expect(discuss()[0].url).toBe("/api/discuss/d1");
    expect(discuss()[0].body).toMatchObject({ session_id: null, message: "想聊結尾", character: "hyena" });
    await screen.findByText("嗯");
    await new Promise(r => setTimeout(r, 30));
    expect(discuss()).toHaveLength(1);
  });
  it("陪讀者選單:選別位 → 送出的 /api/discuss 帶那位;Esc 關閉", async () => {
    mount();
    await box();
    fireEvent.click(screen.getByRole("button", { name: "陪讀者" }));
    const g = within(screen.getByRole("group", { name: "陪讀者" }));
    fireEvent.keyDown(g.getByRole("button", { name: "鬣狗" }), { key: "Escape" });
    expect(screen.queryByRole("group", { name: "陪讀者" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "陪讀者" }));
    fireEvent.click(within(screen.getByRole("group", { name: "陪讀者" })).getByRole("button", { name: "水牛" }));
    fireEvent.change(screen.getByRole("textbox", { name: "對話輸入" }), { target: { value: "嗨" } });
    fireEvent.click(screen.getByRole("button", { name: "送出" }));
    await waitFor(() => expect(discuss()).toHaveLength(1));
    expect(discuss()[0].body.character).toBe("buffalo");
  });
  it("chips 最多 5 個(最近的 5 篇)", async () => {
    works = Array.from({ length: 7 }, (_, i) => W(`d${i}`, `作${i}`, 100 - i));
    mount();
    const g = within(await screen.findByRole("group", { name: "聊哪一篇" }));
    expect(g.getAllByRole("button")).toHaveLength(5);
    expect(g.queryByRole("button", { name: "作5" })).toBeNull();
  });
  it("包在 StrictMode 裡送出也只打一次", async () => {
    mount(true);
    fireEvent.change(await box(), { target: { value: "你好" } });
    fireEvent.click(screen.getByRole("button", { name: "送出" }));
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/w/d2"));
    await screen.findByText("嗯");
    await new Promise(r => setTimeout(r, 30));
    expect(discuss()).toHaveLength(1);
  });
  it("新對話:從作品頁回到 / 並把游標放進輸入框", async () => {
    mount();
    fireEvent.click(within(await screen.findByRole("navigation")).getByRole("button", { name: "海" }));   // 左欄開啟作品
    await screen.findByText("內文一行");
    fireEvent.click(screen.getByRole("button", { name: "新對話" }));   // 收起的左欄也叫這個名字
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/"));
    const b = await box();
    await waitFor(() => expect(document.activeElement).toBe(b));
  });
});

describe("沒有作品", () => {
  beforeEach(() => { works = []; });
  it("沒有 chips;placeholder 是「把稿拖進來,或貼上」;列出每位陪讀者的名字與一句話", async () => {
    mount();
    const b = await box() as HTMLTextAreaElement;
    expect(b.placeholder).toBe("把稿拖進來,或貼上");
    expect(screen.queryByRole("group", { name: "聊哪一篇" })).toBeNull();
    const list = within(screen.getByRole("list", { name: "陪讀者" }));
    for (const n of ["鬣狗", "水牛", "鹿"]) expect(list.getByText(n)).toBeTruthy();
    expect(list.getAllByText("一句話")).toHaveLength(3);
  });
  it("拖 .md 檔:原地出現預估與「交稿」確認鈕,確認後打 /api/stories 並導到新作品", async () => {
    mount();
    await box();
    const home = document.querySelector(".home")!;
    fireEvent.drop(home, { dataTransfer: { files: [new File(["x"], "海.md")] } });
    expect(await screen.findByText("4 字")).toBeTruthy();
    expect(await screen.findByText("第一次分析,還沒有預估。")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /交稿並開始分析/ }));
    await waitFor(() => expect(calls.some(c => c.url === "/api/stories")).toBe(true));
    expect(calls.find(c => c.url === "/api/stories")!.body).toMatchObject({ text: "檔案內容", title: "海" });
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/w/d9"));
  });
  it("貼上 > 2000 字進交稿確認,不進輸入框;短文字照常當訊息", async () => {
    mount();
    const b = await box() as HTMLTextAreaElement;
    fireEvent.paste(b, { clipboardData: { getData: () => "短短的" } });
    expect(screen.queryByRole("button", { name: /交稿並開始分析/ })).toBeNull();
    fireEvent.paste(b, { clipboardData: { getData: () => "字".repeat(2001) } });
    expect(await screen.findByText("2001 字")).toBeTruthy();
    expect(await screen.findByText("預估約 5 分鐘")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(await box()).toBeTruthy();
  });
});

describe("作品清單還沒到 / 抓不到", () => {
  it("載入中:說載入中,不說沒有作品(沒有陪讀者介紹、placeholder 不是空書架那句)", async () => {
    worksFetch = () => new Promise<Response>(() => {});
    mount();
    const b = await box() as HTMLTextAreaElement;
    expect(screen.getByText("載入中……")).toBeTruthy();
    expect(b.placeholder).not.toBe("把稿拖進來,或貼上");
    expect(screen.queryByRole("list", { name: "陪讀者" })).toBeNull();
  });
  it("抓失敗:顯示錯誤,不說沒有作品", async () => {
    worksFetch = async () => { throw new TypeError("down"); };
    mount();
    expect(await screen.findByText("連不上本機的 den,請確認它有在跑。")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toBe("連不上本機的 den,請確認它有在跑。");
    expect(((await box()) as HTMLTextAreaElement).placeholder).not.toBe("把稿拖進來,或貼上");
    expect(screen.queryByRole("list", { name: "陪讀者" })).toBeNull();
  });
});
