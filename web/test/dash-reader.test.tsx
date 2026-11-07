import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within, act } from "@testing-library/react";
import { MemoryRouter, useLocation, useSearchParams } from "react-router-dom";
import Reader, { stateText, shownVersions, dotOf } from "../src/dash/Reader";
import { api, DashError, type WorkDetail } from "../src/dash/api";
import { setLang, translate } from "../src/dash/i18n";
import { LinksProvider } from "../src/dash/links";
import { CharactersProvider, makeCharacters } from "../src/dash/useCharacters";
import { hyena, buffalo, deer } from "./dash-fixtures";
import { setPaperFlow } from "../src/dash/paperFlow";

// 稿文含數字;直排會把短數字包成縱中橫、拆開文字節點。這檔的文字比對一律在橫排做。
beforeEach(() => setPaperFlow("h"));

afterEach(() => vi.unstubAllGlobals());
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
const detail = (over = {}) => ({ slug: "d1", title: "海", version: 2, versions: [1, 2], text: "第一段。\n\n第二段很長。", state: "ready", job_id: null, notes_ready: false, ...over });

function Where() { const l = useLocation(); return <output data-testid="loc">{l.pathname}{l.search}</output>; }
/** 跟 Dash 一樣:網址的 ?v= 決定版本。 */
function Routed(props: { onQuote: (q: string) => void; reload?: number; onOpen?: (s: string) => void }) {
  const [search] = useSearchParams();
  const v = Number(search.get("v"));
  return <Reader slug="d1" version={v > 0 ? v : undefined} onQuote={props.onQuote} reload={props.reload} />;
}
const tree = (onQuote: (q: string) => void, reload?: number, onOpen?: (s: string) => void) => (
  <MemoryRouter initialEntries={["/w/d1"]}>
    <CharactersProvider value={makeCharacters([hyena, buffalo, deer], "hyena")}>
      <LinksProvider><Where /><Routed onQuote={onQuote} reload={reload} onOpen={onOpen} /></LinksProvider>
    </CharactersProvider>
  </MemoryRouter>);
const mount = async (d: object, onQuote = vi.fn(), onOpen?: (s: string) => void) => {
  setLang("zh-Hant");
  const f = vi.fn(async (u: string, init?: RequestInit) => {
    if (u === "/api/jobs") return json({ job_id: 9 }, 202);
    void init;
    const m = /\?v=(\d+)/.exec(u);
    return json(m ? { ...d, version: Number(m[1]), text: `第 ${m[1]} 版的字。` } : d);
  });
  vi.stubGlobal("fetch", f);
  const r = render(tree(onQuote, undefined, onOpen));
  await screen.findByRole("heading", { name: (d as { title?: string }).title ?? "海" });
  return { ...r, onQuote, f };
};
const loc = () => screen.getByTestId("loc").textContent;

describe("Reader(稿窗格)", () => {
  it("顯示最新版原文;版本鍵每版一顆,目前那版 pressed", async () => {
    await mount(detail());
    expect(screen.getByText("第一段。")).toBeTruthy();
    const v1 = screen.getByRole("button", { name: "v1" }), v2 = screen.getByRole("button", { name: "v2" });
    expect(v1.getAttribute("aria-pressed")).toBe("false");
    expect(v2.getAttribute("aria-pressed")).toBe("true");
    expect(screen.queryByText(/這是第/)).toBeNull();
  });
  it("點 v1 → 網址 ?v=1、出現「舊版」膠囊;回到最新版 → 拿掉 ?v=", async () => {
    await mount(detail());
    fireEvent.click(screen.getByRole("button", { name: "v1" }));
    expect(loc()).toBe("/w/d1?v=1");
    expect(await screen.findByText("舊版")).toBeTruthy();
    expect(await screen.findByText("第 1 版的字。")).toBeTruthy();
    expect(screen.getByRole("button", { name: "v1" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "回到最新版" }));
    expect(loc()).toBe("/w/d1");
    expect(await screen.findByText("第一段。")).toBeTruthy();
    expect(screen.queryByText("舊版")).toBeNull();
  });
  it("標題是純文字:沒有 ▾、不是按鈕;也沒有印字頭", async () => {
    const { container } = await mount(detail());
    expect(screen.queryByRole("button", { name: /海/ })).toBeNull();
    expect(screen.getByRole("heading", { name: "海" }).textContent).toBe("海");
    expect(container.querySelector(".dash-printhead, .dash-print")).toBeNull();
  });
  it("5 版:版本條露 3 版,「所有版本」浮層列 5 列各帶日期與點;點 v2 → ?v=2", async () => {
    const day = 86400;
    const history = [1, 2, 3, 4, 5].map(n => ({ n, at: Date.now() / 1000 - (6 - n) * day * 3, analysed: n !== 3, noted: n === 1 }));
    await mount(detail({ version: 5, versions: [1, 2, 3, 4, 5], history }));
    const bar = within(screen.getByRole("group", { name: "版本" }));
    expect(bar.getAllByRole("button", { name: /^v\d$/ }).map(b => b.textContent)).toEqual(["v3", "v4", "v5"]);
    fireEvent.click(bar.getByRole("button", { name: "所有版本" }));
    const dlg = within(screen.getByRole("dialog", { name: "所有版本" }));
    const rows = dlg.getAllByRole("button");
    expect(rows).toHaveLength(5);
    expect(rows[0].querySelector(".vdot")!.getAttribute("data-dot")).toBe("full");
    expect(rows[1].querySelector(".vdot")!.getAttribute("data-dot")).toBe("half");
    expect(rows[2].querySelector(".vdot")!.getAttribute("data-dot")).toBe("empty");
    expect(rows.every(r => r.querySelector(".vdot-when")!.textContent!.length > 0)).toBe(true);
    fireEvent.click(rows[1]);
    expect(loc()).toBe("/w/d1?v=2");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
  it("所有版本浮層按 Esc 關", async () => {
    await mount(detail({ version: 4, versions: [1, 2, 3, 4] }));
    fireEvent.click(screen.getByRole("button", { name: "所有版本" }));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
  it("稿頂排法:按橫排 → 稿變 data-flow=h", async () => {
    const { container } = await mount(detail());
    setPaperFlow("v");
    fireEvent.click(within(screen.getByRole("group", { name: "排法" })).getByRole("button", { name: "橫排" }));
    expect(container.querySelector("article")!.dataset.flow).toBe("h");
  });
  it("原文第一行就是標題(含《》)時不重複顯示;不同的第一行照留", async () => {
    await mount(detail({ text: "《海》\n\n第一段。" }));
    expect(screen.getAllByText(/海/)).toHaveLength(1);
    expect(screen.getByText("第一段。")).toBeTruthy();
  });
  it("標題與第一行只差全半形標點也算同一個", async () => {
    await mount(detail({ title: "海,開賣啦!", text: "《海，開賣啦！》\n\n第一段。" }));
    expect(screen.queryByText("《海，開賣啦！》")).toBeNull();
  });
  it("第一行只是提到標題的句子時不拿掉", async () => {
    await mount(detail({ text: "海很深。\n\n第一段。" }));
    expect(screen.getByText("海很深。")).toBeTruthy();
  });
  it("未分析的作品也能讀", async () => {
    await mount(detail({ state: "none", version: 1, versions: [1] }));
    expect(screen.getByText("第二段很長。")).toBeTruthy();
    expect(screen.getByRole("button", { name: "分析" })).toBeTruthy();
    expect(document.querySelector(".paper-state")).toBeNull();
  });
  it("選一段 → 帶進對話,送出引用", async () => {
    const { onQuote } = await mount(detail());
    const range = document.createRange();
    const node = screen.getByText("第一段。").firstChild!;
    range.setStart(node, 0); range.setEnd(node, 3);
    document.getSelection()!.removeAllRanges(); document.getSelection()!.addRange(range);
    document.dispatchEvent(new Event("selectionchange"));
    fireEvent.click(await screen.findByRole("button", { name: "帶進對話" }));
    expect(onQuote).toHaveBeenCalledWith("第一段");
  });
  it("選到標題不會出現帶進對話的鈕(只收正文)", async () => {
    await mount(detail());
    const range = document.createRange();
    range.selectNodeContents(screen.getByRole("heading", { name: "海" }));
    document.getSelection()!.removeAllRanges(); document.getSelection()!.addRange(range);
    document.dispatchEvent(new Event("selectionchange"));
    expect(screen.queryByRole("button", { name: "帶進對話" })).toBeNull();
  });
  it("載入失敗顯示對應訊息", async () => {
    setLang("zh-Hant");
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "x", code: "unknown-work" }, 404)));
    render(tree(vi.fn()));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "找不到這篇作品。");
  });
  it.each([["stopped", "停住了"], ["notes-stopped", "筆記停住了"]])("狀態 %s:說停住了,附續跑(只續跑,不重開)", async (state, line) => {
    const { f } = await mount(detail({ state }));
    expect(screen.getByText(line)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "續跑" }));
    await waitFor(() => expect(f.mock.calls.some(c => c[0] === "/api/jobs")).toBe(true));
    const call = f.mock.calls.find(c => c[0] === "/api/jobs")!;
    expect(JSON.parse(String(call[1]!.body))).toMatchObject({ kind: "critique", slug: "d1", resume_only: true });
  });
  it("續跑過(重抓過)之後換版本:新版回來前不留著舊的字", async () => {
    const { f } = await mount(detail({ state: "stopped" }));
    fireEvent.click(screen.getByRole("button", { name: "續跑" }));
    await waitFor(() => expect(f.mock.calls.filter(c => c[0] === "/api/works/d1").length).toBe(2));
    const inner = f.getMockImplementation()!;
    f.mockImplementation(async (u: string, init?: RequestInit) => (u.includes("?v=") ? new Promise<Response>(() => {}) : inner(u, init)));
    fireEvent.click(screen.getByRole("button", { name: "v1" }));
    await waitFor(() => expect(screen.queryByText("第一段。")).toBeNull());
    expect(screen.getByText("載入中……")).toBeTruthy();
  });
  it("沒停住就沒有續跑鍵", async () => {
    await mount(detail());
    expect(screen.queryByRole("button", { name: "續跑" })).toBeNull();
  });
  it("reload 遞增 → 同一篇重抓", async () => {
    const { rerender, f } = await mount(detail());
    const n = f.mock.calls.length;
    rerender(tree(vi.fn(), 1));
    await waitFor(() => expect(f.mock.calls.length).toBe(n + 1));
  });
});

describe("stateText", () => {
  it.each([
    ["running", "分析中"],
    ["notes-running", "筆記還在寫"],
    ["notes-stopped", "筆記停住了"],
    ["stopped", "停住了"],
  ])("%s → %s", (state, text) => {
    expect(translate("zh-Hant", stateText(state)!)).toBe(text);
  });
  it.each(["ready", "stale", "none"])("%s:版本點已經表達,不出字", state => {
    expect(stateText(state)).toBeNull();
  });
});

describe("分析進度", () => {
  const work = (o: object) => ({ slug: "d1", title: "海", version: 2, text: "內文", state: "ready", job_id: null, notes_ready: true, versions: [2], ...o });
  const mountSpy = (w: object, onFinished = vi.fn()) => {
    setLang("zh-Hant");
    vi.spyOn(api, "work").mockResolvedValue(w as WorkDetail);
    if (!vi.isMockFunction(api.job)) vi.spyOn(api, "job").mockReturnValue(new Promise(() => {}));
    render(<MemoryRouter><CharactersProvider value={makeCharacters([hyena], "hyena")}><LinksProvider>
      <Reader slug="d1" onQuote={vi.fn()} onFinished={onFinished} />
    </LinksProvider></CharactersProvider></MemoryRouter>);
    return onFinished;
  };
  afterEach(() => vi.restoreAllMocks());
  it("顯示步驟;done 後重抓這篇並通知左欄", async () => {
    vi.spyOn(api, "jobEvents").mockImplementation(async function* () {
      yield { event: "phase", data: { name: "analyst", status: "start" } };
      yield { event: "done", data: { ok: true } };
    });
    const onFinished = mountSpy(work({ state: "running", job_id: 5, notes_ready: false }));
    await waitFor(() => expect(onFinished).toHaveBeenCalled());
    await waitFor(() => expect(api.work).toHaveBeenCalledTimes(2));
  });
  it("SSE 送來的步驟蓋過作品 state", async () => {
    vi.spyOn(api, "jobEvents").mockImplementation(async function* () {
      yield { event: "phase", data: { name: "reviewer", status: "start" } };
      await new Promise(() => {});
    });
    mountSpy(work({ state: "running", job_id: 5 }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("寫筆記"));
  });
  it("只收到終態 state 事件(已結束的 job)也算結束,重抓並通知", async () => {
    vi.spyOn(api, "jobEvents").mockImplementation(async function* () {
      yield { event: "state", data: { state: "done", step: null } };
    });
    const onFinished = mountSpy(work({ state: "running", job_id: 5 }));
    await waitFor(() => expect(onFinished).toHaveBeenCalled());
    await waitFor(() => expect(api.work).toHaveBeenCalledTimes(2));
  });
  it("串流沒收尾就斷了也算結束", async () => {
    vi.spyOn(api, "jobEvents").mockImplementation(async function* () { /* 空串流 */ });
    const onFinished = mountSpy(work({ state: "running", job_id: 5 }));
    await waitFor(() => expect(onFinished).toHaveBeenCalled());
  });
  it("稿窗格頂列不再有筆記鍵(筆記在右欄分頁)", async () => {
    mountSpy(work({}));
    await screen.findByText("內文");
    expect(screen.queryByRole("button", { name: /筆記/ })).toBeNull();
  });
});

describe("稿頂分析進度", () => {
  const T0 = 1_800_000_000;
  const work = (o: object) => ({ slug: "d1", title: "海", version: 2, text: "內文", state: "running", job_id: 7, notes_ready: false, versions: [2], ...o });
  const hang = () => vi.spyOn(api, "jobEvents").mockImplementation(async function* () { await new Promise(() => {}); });
  const jobIs = (o: object = {}) => vi.spyOn(api, "job").mockResolvedValue({ id: 7, state: "running", step: null, created_at: T0 - 65, ...o });
  const mount = (w: object, onFinished = vi.fn()) => {
    setLang("zh-Hant");
    vi.spyOn(api, "work").mockResolvedValue(w as WorkDetail);
    render(<MemoryRouter><CharactersProvider value={makeCharacters([hyena], "hyena")}><LinksProvider>
      <Reader slug="d1" onQuote={vi.fn()} onFinished={onFinished} />
    </LinksProvider></CharactersProvider></MemoryRouter>);
    return onFinished;
  };
  const running = () => document.querySelector(".paper-top .running");
  beforeEach(() => { vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] }); vi.setSystemTime(T0 * 1000); });
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

  it("觀察中、從 job 的 created_at 接著算、每秒走;不再說「分析中」", async () => {
    hang(); jobIs();
    mount(work({}));
    await screen.findByText("1:05");
    expect(running()!.textContent).toContain("觀察中");
    act(() => { vi.advanceTimersByTime(1000); });
    expect(screen.getByText("1:06")).toBeTruthy();
    expect(screen.queryByText("分析中")).toBeNull();
    expect(document.querySelector(".paper-top .paper-track")).not.toBeNull();
  });
  it("重新整理後 SSE 還沒送步驟:notes-running → 寫筆記", async () => {
    hang(); jobIs();
    mount(work({ state: "notes-running" }));
    await screen.findByText("1:05");
    expect(running()!.textContent).toContain("寫筆記");
  });
  it("job 還在排隊:有步驟字、沒有計時", async () => {
    hang(); jobIs({ state: "queued" });
    mount(work({}));
    await waitFor(() => expect(api.job).toHaveBeenCalledWith(7));
    await act(async () => { await Promise.resolve(); });
    expect(running()!.textContent).toContain("觀察中");
    expect(running()!.querySelector(".t")).toBeNull();
  });
  it("掛上時還在排隊、之後 SSE 送來步驟 → 重抓 job,計時出現", async () => {
    vi.useRealTimers();
    let push!: () => void;
    const started = new Promise<void>(r => { push = r; });
    vi.spyOn(api, "jobEvents").mockImplementation(async function* () {
      await started;
      yield { event: "phase", data: { name: "analyst", status: "start" } };
      await new Promise(() => {});
    });
    const job = vi.spyOn(api, "job").mockResolvedValueOnce({ id: 7, state: "queued", step: null, created_at: 1 })
      .mockResolvedValue({ id: 7, state: "running", step: "analyst", created_at: Date.now() / 1000 - 3 });
    mount(work({}));
    await waitFor(() => expect(job).toHaveBeenCalledTimes(1));
    expect(running()!.querySelector(".t")).toBeNull();
    push();
    await waitFor(() => expect(running()!.querySelector(".t")).not.toBeNull());
    expect(job).toHaveBeenCalledTimes(2);
  });
  it("停下:打 cancel,之後重抓這篇", async () => {
    vi.useRealTimers();
    hang(); jobIs();
    const cancel = vi.spyOn(api, "cancelJob").mockResolvedValue({ ok: true });
    const onFinished = mount(work({}));
    const stop = await screen.findByRole("button", { name: "停下" });
    expect(stop.querySelector("svg.ico")).not.toBeNull();
    fireEvent.click(stop);
    expect(cancel).toHaveBeenCalledWith(7);
    await waitFor(() => expect(api.work).toHaveBeenCalledTimes(2));
    expect(onFinished).toHaveBeenCalled();
  });
  it("停下時 job 剛好跑完(409):不報錯,照樣重抓", async () => {
    vi.useRealTimers();
    hang(); jobIs();
    vi.spyOn(api, "cancelJob").mockRejectedValue(new DashError(409, "unknown"));
    mount(work({}));
    fireEvent.click(await screen.findByRole("button", { name: "停下" }));
    await waitFor(() => expect(api.work).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("alert")).toBeNull();
  });
  it("抓 job 失敗:只顯示步驟字", async () => {
    hang(); vi.spyOn(api, "job").mockRejectedValue(new DashError(0, "den-down"));
    mount(work({}));
    await waitFor(() => expect(running()).not.toBeNull());
    await act(async () => { await Promise.resolve(); });
    expect(running()!.textContent).toContain("觀察中");
    expect(running()!.querySelector(".t")).toBeNull();
  });
  it.each([["ready", false], ["stopped", true], ["stale", false]])("%s:沒有進度與鉛筆線;只有停住才出狀態字", async (state, says) => {
    mount(work({ state, job_id: null }));
    await screen.findByText("內文");
    expect(running()).toBeNull();
    expect(document.querySelector(".paper-top .paper-track")).toBeNull();
    expect(!!document.querySelector(".paper-state")).toBe(says);
  });
});

describe("版本條規則", () => {
  it("shownVersions", () => {
    expect(shownVersions([1], 1)).toEqual({ more: false, list: [1] });
    expect(shownVersions([1, 2, 3], 1)).toEqual({ more: false, list: [1, 2, 3] });
    expect(shownVersions([1, 2, 3, 4, 5], 5)).toEqual({ more: true, list: [3, 4, 5] });
    expect(shownVersions([1, 2, 3, 4, 5], 1)).toEqual({ more: true, list: [1, 4, 5] });
    expect(shownVersions([1, 2, 3, 4, 5], 4)).toEqual({ more: true, list: [3, 4, 5] });
  });
  it("dotOf", () => {
    expect(dotOf({ analysed: false, noted: false })).toEqual({ dot: "empty", busy: false });
    expect(dotOf({ analysed: true, noted: false })).toEqual({ dot: "half", busy: false });
    expect(dotOf({ analysed: true, noted: true })).toEqual({ dot: "full", busy: false });
    expect(dotOf({ analysed: false, noted: false }, "running")).toEqual({ dot: "empty", busy: true });
    expect(dotOf({ analysed: true, noted: false }, "notes-running")).toEqual({ dot: "half", busy: true });
  });
});

describe("交新版", () => {
  const file = () => new File(["改過的稿"], "海2.md", { type: "text/markdown" });
  type R = { same: boolean; version: number; analyzing: boolean };
  const mountNew = async (over: object = {}, path = "/w/d1") => {
    setLang("zh-Hant");
    vi.spyOn(api, "work").mockImplementation(async (_s, v) => detail({ ...over, ...(v ? { version: v, text: `第 ${v} 版的字。` } : {}) }) as WorkDetail);
    vi.spyOn(api, "extract").mockResolvedValue({ filename: "海2.md", text: "改過的稿", chars: 4 });
    vi.spyOn(api, "estimate").mockResolvedValue(null);
    vi.spyOn(api, "submit").mockResolvedValue({ slug: "d1", title: "海", version: 3, new_version: true, reused: false });
    vi.spyOn(api, "startJob").mockResolvedValue({ job_id: 9 });
    const onNewVersion = vi.fn<(r: R) => void>();
    const onFinished = vi.fn();
    function R2() {
      const [search] = useSearchParams();
      const v = Number(search.get("v"));
      return <Reader slug="d1" version={v > 0 ? v : undefined} onQuote={vi.fn()}
        onNewVersion={onNewVersion} onFinished={onFinished} />;
    }
    const r = render(<MemoryRouter initialEntries={[path]}><CharactersProvider value={makeCharacters([hyena], "hyena")}><LinksProvider>
      <R2 /></LinksProvider></CharactersProvider></MemoryRouter>);
    await screen.findByRole("heading", { name: "海" });
    return { ...r, onNewVersion, onFinished };
  };
  const pick = (c: HTMLElement) => fireEvent.change(c.querySelector('input[type="file"]')!, { target: { files: [file()] } });
  afterEach(() => vi.restoreAllMocks());

  it("頂列有交新版鍵;選檔後出現「v3」交稿條", async () => {
    const { container } = await mountNew();
    expect(screen.getByRole("button", { name: "交新版" })).toBeTruthy();
    pick(container);
    expect(await screen.findByText("v3")).toBeTruthy();
    expect(api.extract).toHaveBeenCalled();
    expect(screen.getByText("4 字")).toBeTruthy();
    expect(screen.queryByText(/預估/)).toBeNull();
    expect(screen.getByText("會花額度")).toBeTruthy();
  });
  it("在 ?v=1 開交稿條也是第 3 版", async () => {
    const { container } = await mountNew({}, "/w/d1?v=1");
    await screen.findByText("第 1 版的字。");
    pick(container);
    expect(await screen.findByText("v3")).toBeTruthy();
  });
  it("交出去並分析 → submit 帶 slug、startJob、onNewVersion 收到 analyzing:true、交稿條消失", async () => {
    const { container, onNewVersion } = await mountNew();
    pick(container);
    fireEvent.click(await screen.findByRole("button", { name: "分析" }));
    await waitFor(() => expect(onNewVersion).toHaveBeenCalledWith({ same: false, version: 3, analyzing: true }));
    expect(api.submit).toHaveBeenCalledWith("改過的稿", undefined, "d1");
    expect(api.startJob).toHaveBeenCalledWith("d1");
    expect(screen.queryByText("v3")).toBeNull();
  });
  it("只存版 → 不開 job,onNewVersion 收到 analyzing:false", async () => {
    const { container, onNewVersion } = await mountNew();
    pick(container);
    fireEvent.click(await screen.findByRole("button", { name: "只存" }));
    await waitFor(() => expect(onNewVersion).toHaveBeenCalledWith({ same: false, version: 3, analyzing: false }));
    expect(api.startJob).not.toHaveBeenCalled();
  });
  it("submit 失敗(story-too-long)→ 交稿條顯示錯誤、稿留著", async () => {
    const { container, onNewVersion } = await mountNew();
    vi.mocked(api.submit).mockRejectedValue(new DashError(413, "story-too-long"));
    pick(container);
    fireEvent.click(await screen.findByRole("button", { name: "分析" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("v3")).toBeTruthy();
    expect(onNewVersion).not.toHaveBeenCalled();
  });
  it("跟最新版一字不差 → onNewVersion 收到 same:true 與那一版的號碼", async () => {
    const { container, onNewVersion } = await mountNew();
    vi.mocked(api.submit).mockResolvedValue({ slug: "d1", title: "海", version: 2, new_version: false, reused: true });
    pick(container);
    fireEvent.click(await screen.findByRole("button", { name: "分析" }));
    await waitFor(() => expect(onNewVersion).toHaveBeenCalledWith({ same: true, version: 2, analyzing: false }));
  });
  it("確認還在跑時換了作品 → 結果回來不再通知 onNewVersion", async () => {
    setLang("zh-Hant");
    vi.spyOn(api, "work").mockImplementation(async s => detail({ slug: s }) as WorkDetail);
    vi.spyOn(api, "extract").mockResolvedValue({ filename: "海2.md", text: "改過的稿", chars: 4 });
    vi.spyOn(api, "estimate").mockResolvedValue(null);
    let done!: (r: Awaited<ReturnType<typeof api.submit>>) => void;
    vi.spyOn(api, "submit").mockReturnValue(new Promise(res => { done = res; }));
    vi.spyOn(api, "startJob").mockResolvedValue({ job_id: 9 });
    const onNewVersion = vi.fn();
    const el = (slug: string) => <MemoryRouter><CharactersProvider value={makeCharacters([hyena], "hyena")}><LinksProvider>
      <Reader slug={slug} onQuote={vi.fn()} onNewVersion={onNewVersion} />
    </LinksProvider></CharactersProvider></MemoryRouter>;
    const { container, rerender } = render(el("d1"));
    await screen.findByRole("heading", { name: "海" });
    pick(container);
    fireEvent.click(await screen.findByRole("button", { name: "只存" }));
    await waitFor(() => expect(api.submit).toHaveBeenCalled());
    rerender(el("d2"));
    done({ slug: "d1", title: "海", version: 3, new_version: true, reused: false });
    await new Promise(r => setTimeout(r, 30));
    expect(onNewVersion).not.toHaveBeenCalled();
  });
  it("只有空白的檔 → 交稿條說稿子是空的,兩顆送出鍵 disabled", async () => {
    const { container } = await mountNew();
    vi.mocked(api.extract).mockResolvedValue({ filename: "a.md", text: "  \n ", chars: 3 });
    pick(container);
    expect((await screen.findByRole("alert")).textContent).toBe("稿子是空的。");
    expect(screen.getByRole("button", { name: "只存" })).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "分析" })).toHaveProperty("disabled", true);
  });
  it("新版存下了但開分析失敗 → 照樣回最新版(analyzing:false),頂列顯示錯誤", async () => {
    const { container, onNewVersion } = await mountNew();
    vi.mocked(api.startJob).mockRejectedValue(new DashError(503, "den-down"));
    pick(container);
    fireEvent.click(await screen.findByRole("button", { name: "分析" }));
    await waitFor(() => expect(onNewVersion).toHaveBeenCalledWith({ same: false, version: 3, analyzing: false }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText("v3")).toBeNull();
  });
  it("送出中:取消 disabled、按的那顆說送出中、選檔不換稿", async () => {
    const { container, onNewVersion } = await mountNew();
    let done!: (v: never) => void;
    vi.mocked(api.submit).mockImplementation(() => new Promise(r => { done = r as never; }));
    pick(container);
    fireEvent.click(await screen.findByRole("button", { name: "只存" }));
    expect(await screen.findByRole("button", { name: "送出中……" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "取消" })).toHaveProperty("disabled", true);
    pick(container);
    expect(api.extract).toHaveBeenCalledTimes(1);
    done({ slug: "d1", title: "海", version: 3, new_version: true, reused: false } as never);
    await waitFor(() => expect(onNewVersion).toHaveBeenCalledWith({ same: false, version: 3, analyzing: false }));
  });
  it("取消 → 交稿條消失", async () => {
    const { container } = await mountNew();
    pick(container);
    fireEvent.click(await screen.findByRole("button", { name: "取消" }));
    expect(screen.queryByText("v3")).toBeNull();
  });
  it("把檔拖到畫面任何地方 → 出現交稿條", async () => {
    await mountNew();
    fireEvent.drop(window, { dataTransfer: { types: ["Files"], files: [file()] } });
    expect(await screen.findByText("v3")).toBeTruthy();
  });
  it("state=stale 的最新版有「分析」;按下 startJob(slug)、重抓並通知", async () => {
    const { onFinished } = await mountNew({ state: "stale" });
    fireEvent.click(screen.getByRole("button", { name: "分析" }));
    await waitFor(() => expect(onFinished).toHaveBeenCalled());
    expect(api.startJob).toHaveBeenCalledWith("d1");
    await waitFor(() => expect(api.work).toHaveBeenCalledTimes(2));
  });
  it("分析失敗 → 顯示錯誤", async () => {
    await mountNew({ state: "none" });
    vi.mocked(api.startJob).mockRejectedValue(new DashError(409, "busy"));
    fireEvent.click(screen.getByRole("button", { name: "分析" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
  it("state=ready 時沒有「分析」", async () => {
    await mountNew({ state: "ready" });
    expect(screen.queryByRole("button", { name: "分析" })).toBeNull();
  });
  it("看 ?v=1 時沒有「分析」", async () => {
    await mountNew({ state: "stale" }, "/w/d1?v=1");
    await screen.findByText("第 1 版的字。");
    expect(screen.queryByRole("button", { name: "分析" })).toBeNull();
  });
});
