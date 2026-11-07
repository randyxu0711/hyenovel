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

function Where() { const l = useLocation(); return <output data-testid="loc">{l.pathname}</output>; }
function mount() {
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
  render(tree);
}
const box = () => screen.findByRole("textbox", { name: "貼上或拖進一篇稿" });
const confirmBtn = () => screen.queryByRole("button", { name: "分析" });

beforeEach(() => {
  setLang("zh-Hant"); localStorage.clear(); serverDefault = "hyena"; calls = [];
  works = [W("d2", "海", 200), W("d1", "山", 100)]; sessionRows = []; worksFetch = null;
});
afterEach(() => vi.unstubAllGlobals());

describe("進門只有一張紙", () => {
  it("有作品:只有交稿的紙,沒有 chips、讀完那句、陪讀者介紹、送出鈕", async () => {
    mount();
    await box();
    await waitFor(() => expect(calls.some(c => c.url === "/api/works")).toBe(true));
    const paper = document.querySelector(".home form.composer")!;
    expect(paper).not.toBeNull();
    const pick = within(paper as HTMLElement).getByRole("button", { name: "交稿" });
    expect(pick.querySelector("svg.ico")).not.toBeNull();
    expect(screen.queryByRole("group", { name: "聊哪一篇" })).toBeNull();
    expect(screen.queryByText(/讀完了/)).toBeNull();
    expect(screen.queryByRole("list", { name: "陪讀者" })).toBeNull();
    expect(screen.queryByRole("button", { name: "送出" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^陪讀者/ })).toBeNull();
    expect(document.querySelector(".home-first")).toBeNull();
    expect(calls.some(c => c.url.endsWith("/sessions"))).toBe(false);
  });
  it("紙上的角色是預設陪讀者", async () => {
    serverDefault = "deer";
    mount();
    await box();
    expect(document.querySelector(".home form.composer svg.fig")!.getAttribute("data-who")).toBe("deer");
  });
  it("打很長的字按 Enter → 交稿確認條;短字按 Enter 什麼都不發生;組字中不觸發", async () => {
    mount();
    const b = await box();
    fireEvent.change(b, { target: { value: "短短五個字" } });
    fireEvent.keyDown(b, { key: "Enter" });
    expect(confirmBtn()).toBeNull();
    expect(screen.getByTestId("loc").textContent).toBe("/");
    fireEvent.change(b, { target: { value: "字".repeat(2001) } });
    fireEvent.keyDown(b, { key: "Enter", isComposing: true });
    expect(confirmBtn()).toBeNull();
    fireEvent.keyDown(b, { key: "Enter" });
    expect(await screen.findByText("2001 字")).toBeTruthy();
    expect(confirmBtn()).not.toBeNull();
  });
  it("交稿鈕開檔案選擇(只收 .md/.txt),選了檔進確認條", async () => {
    mount();
    await box();
    const input = document.querySelector('.home input[type=file]') as HTMLInputElement;
    expect(input.accept).toBe(".md,.txt");
    const click = vi.spyOn(input, "click").mockImplementation(() => {});
    fireEvent.click(screen.getByRole("button", { name: "交稿" }));
    expect(click).toHaveBeenCalled();
    fireEvent.change(input, { target: { files: [new File(["x"], "海.md")] } });
    expect(await screen.findByText("4 字")).toBeTruthy();
  });
  it("交新稿:從作品頁回到 / 並把游標放進紙裡", async () => {
    localStorage.setItem("hyenovel.shelf", "open");
    mount();
    fireEvent.click(within(await screen.findByRole("navigation")).getByRole("button", { name: /^海/ }));
    await screen.findByText("內文一行");
    fireEvent.click(screen.getByRole("button", { name: "交一篇新稿" }));
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/"));
    const b = await box();
    await waitFor(() => expect(document.activeElement).toBe(b));
  });
});

describe("沒有作品", () => {
  beforeEach(() => { works = []; });
  it("紙上方不多一句提示(placeholder 已經說了)", async () => {
    mount();
    await box();
    expect(document.querySelector(".home-first")).toBeNull();
  });
  it("拖 .md 檔:原地出現預估與「交稿」確認鈕,確認後打 /api/stories 並導到新作品", async () => {
    mount();
    await box();
    const home = document.querySelector(".home")!;
    fireEvent.drop(home, { dataTransfer: { files: [new File(["x"], "海.md")] } });
    expect(await screen.findByText("4 字")).toBeTruthy();
    expect(screen.queryByText(/預估/)).toBeNull();
    expect(screen.getByText("會花額度")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "分析" }));
    await waitFor(() => expect(calls.some(c => c.url === "/api/stories")).toBe(true));
    expect(calls.find(c => c.url === "/api/stories")!.body).toMatchObject({ text: "檔案內容", title: "海" });
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toBe("/w/d9"));
  });
  it("貼上 > 2000 字進交稿確認,不進紙;短文字照常留在紙上", async () => {
    mount();
    const b = await box() as HTMLTextAreaElement;
    fireEvent.paste(b, { clipboardData: { getData: () => "短短的" } });
    expect(confirmBtn()).toBeNull();
    fireEvent.paste(b, { clipboardData: { getData: () => "字".repeat(2001) } });
    expect(await screen.findByText("2001 字")).toBeTruthy();
    expect(await screen.findByText("約 5 分")).toBeTruthy();
    expect(document.querySelector(".home-draft.composer")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
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
