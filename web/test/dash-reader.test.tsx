import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation, useSearchParams } from "react-router-dom";
import Reader, { stateText } from "../src/dash/Reader";
import { setLang, translate } from "../src/dash/i18n";
import { LinksProvider } from "../src/dash/links";
import { CharactersProvider, makeCharacters } from "../src/dash/useCharacters";
import { hyena, buffalo, deer } from "./dash-fixtures";

afterEach(() => vi.unstubAllGlobals());
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
const detail = (over = {}) => ({ slug: "d1", title: "海", version: 2, versions: [1, 2], text: "第一段。\n\n第二段很長。", state: "ready", job_id: null, notes_ready: false, ...over });

function Where() { const l = useLocation(); return <output data-testid="loc">{l.pathname}{l.search}</output>; }
/** 跟 Dash 一樣:網址的 ?v= 決定版本。 */
function Routed(props: { onQuote: (q: string) => void; reload?: number; onOpen?: (s: string) => void }) {
  const [search] = useSearchParams();
  const v = Number(search.get("v"));
  return <Reader slug="d1" version={v > 0 ? v : undefined} works={[{ slug: "d1", title: "海", version: 2, chars: 9, updated_at: 1, state: "ready" }, { slug: "d2", title: "山", version: 1, chars: 3, updated_at: 0, state: "none" }]}
    onOpen={props.onOpen ?? vi.fn()} onSubmitNew={vi.fn()} onQuote={props.onQuote} reload={props.reload} />;
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
  it("點 v1 → 網址 ?v=1、出現「這是第 1 版」;回到最新版 → 拿掉 ?v=", async () => {
    await mount(detail());
    fireEvent.click(screen.getByRole("button", { name: "v1" }));
    expect(loc()).toBe("/w/d1?v=1");
    expect(await screen.findByText("這是第 1 版")).toBeTruthy();
    expect(await screen.findByText("第 1 版的字。")).toBeTruthy();
    expect(screen.getByRole("button", { name: "v1" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "回到最新版" }));
    expect(loc()).toBe("/w/d1");
    expect(await screen.findByText("第一段。")).toBeTruthy();
    expect(screen.queryByText(/這是第/)).toBeNull();
  });
  it("標題鍵打開作品浮層,選另一篇", async () => {
    const onOpen = vi.fn();
    await mount(detail(), vi.fn(), onOpen);
    fireEvent.click(screen.getByRole("button", { name: "海" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /山/ }));
    expect(onOpen).toHaveBeenCalledWith("d2");
    expect(screen.queryByRole("dialog")).toBeNull();
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
    expect(screen.getByText("還沒分析")).toBeTruthy();
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
  it.each([["stopped", "分析停住了"], ["notes-stopped", "筆記停住了"]])("狀態 %s:說停住了,附續跑(只續跑,不重開)", async (state, line) => {
    const { f } = await mount(detail({ state }));
    expect(screen.getByText(line)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "續跑" }));
    await waitFor(() => expect(f.mock.calls.some(c => c[0] === "/api/jobs")).toBe(true));
    const call = f.mock.calls.find(c => c[0] === "/api/jobs")!;
    expect(JSON.parse(String(call[1]!.body))).toMatchObject({ kind: "critique", slug: "d1", resume_only: true });
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
    ["running", false, "分析中"],
    ["notes-running", false, "分析好了,筆記還在寫"],
    ["notes-stopped", false, "筆記停住了"],
    ["ready", true, "分析和筆記都好了"],
    ["ready", false, "分析好了"],
    ["stopped", false, "分析停住了"],
    ["stale", false, "新版還沒分析"],
    ["none", false, "還沒分析"],
  ])("%s(notes_ready=%s)→ %s", (state, notes, text) => {
    expect(translate("zh-Hant", stateText(state, notes))).toBe(text);
  });
  it("兩種語言都有", () => {
    for (const s of ["running", "notes-running", "notes-stopped", "ready", "stopped", "stale", "none"])
      expect(translate("en", stateText(s, s === "ready"))).not.toBe(translate("zh-Hant", stateText(s, s === "ready")));
  });
});
