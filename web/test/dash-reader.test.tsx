import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, act, fireEvent, waitFor } from "@testing-library/react";
import Reader from "../src/dash/Reader";
import { setLang } from "../src/dash/i18n";
import { CharactersProvider, makeCharacters } from "../src/dash/useCharacters";
import { hyena, buffalo, deer } from "./dash-fixtures";

afterEach(() => vi.unstubAllGlobals());
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
const detail = (over = {}) => ({ slug: "d1", title: "海", version: 2, text: "第一段。\n\n第二段很長。", state: "ready", job_id: null, notes_ready: false, ...over });
const mount = async (d: object, onQuote = vi.fn()) => {
  setLang("zh-Hant");
  vi.stubGlobal("fetch", vi.fn(async () => json(d)));
  const r = render(
    <CharactersProvider value={makeCharacters([hyena, buffalo, deer], "hyena")}>
      <Reader slug="d1" companion="鬣狗" onQuote={onQuote} />
    </CharactersProvider>);
  await screen.findByText((d as { title?: string }).title ?? "海");
  return { ...r, onQuote };
};
const select = (node: Node, len: number) => {
  const range = document.createRange();
  range.setStart(node, 0); range.setEnd(node, len);
  const sel = document.getSelection()!;
  sel.removeAllRanges(); sel.addRange(range);
  act(() => { document.dispatchEvent(new Event("selectionchange")); });
};

describe("Reader", () => {
  it("顯示最新版原文與版本", async () => {
    await mount(detail());
    expect(screen.getByText("第一段。")).toBeTruthy();
    expect(screen.getByText("第 2 版")).toBeTruthy();
  });
  it("原文第一行就是標題(含《》)時不重複顯示;不同的第一行照留", async () => {
    await mount(detail({ text: "《海》\n\n第一段。" }));
    expect(screen.getAllByText(/海/)).toHaveLength(1);
    expect(screen.getByText("第一段。")).toBeTruthy();
    vi.unstubAllGlobals();
  });
  it("標題與第一行只差全半形標點也算同一個", async () => {
    await mount(detail({ title: "海,開賣啦!", text: "《海，開賣啦！》\n\n第一段。" }));
    expect(screen.queryByText("《海，開賣啦！》")).toBeNull();
    vi.unstubAllGlobals();
  });
  it("第一行只是提到標題的句子時不拿掉", async () => {
    await mount(detail({ text: "海很深。\n\n第一段。" }));
    expect(screen.getByText("海很深。")).toBeTruthy();
  });
  it("未分析的作品也能讀", async () => {
    await mount(detail({ state: "none", version: 1 }));
    expect(screen.getByText("第二段很長。")).toBeTruthy();
  });
  it("選一段 → 帶給鬣狗聊,按下送出引用並清掉", async () => {
    const { onQuote } = await mount(detail());
    select(screen.getByText("第一段。").firstChild!, 3);
    fireEvent.click(await screen.findByRole("button", { name: "帶給鬣狗聊" }));
    expect(onQuote).toHaveBeenCalledWith("第一段");
    expect(screen.queryByRole("button", { name: "帶給鬣狗聊" })).toBeNull();
  });
  it("超過 400 字:按鈕 disabled 並提示", async () => {
    await mount(detail({ text: "字".repeat(450) }));
    select(screen.getByText("字".repeat(450)).firstChild!, 450);
    const btn = await screen.findByRole("button", { name: "帶給鬣狗聊" }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(screen.getByText("選短一點(400 字內)")).toBeTruthy();
  });
  it("載入失敗顯示對應訊息", async () => {
    setLang("zh-Hant");
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "x", code: "unknown-work" }, 404)));
    render(<CharactersProvider value={makeCharacters([hyena], "hyena")}><Reader slug="zz" companion="鬣狗" onQuote={vi.fn()} /></CharactersProvider>);
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "找不到這篇作品。");
  });
  it("選到標題不會出現帶進對話的鈕(只收正文)", async () => {
    await mount(detail());
    select(screen.getByRole("heading", { name: "海" }).firstChild!, 1);
    expect(screen.queryByRole("button", { name: "帶給鬣狗聊" })).toBeNull();
  });
  it.each([["stopped", "分析停住了"], ["notes-stopped", "備課筆記停住了"]])("狀態 %s:進度區明說停住了", async (state, line) => {
    await mount(detail({ state }));
    expect(screen.getByText(line)).toBeTruthy();
  });
  it("reload 遞增 → 同一篇重抓", async () => {
    const { rerender } = await mount(detail());
    const f = fetch as unknown as ReturnType<typeof vi.fn>;
    const n = f.mock.calls.length;
    rerender(
      <CharactersProvider value={makeCharacters([hyena, buffalo, deer], "hyena")}>
        <Reader slug="d1" companion="鬣狗" onQuote={vi.fn()} reload={1} />
      </CharactersProvider>);
    await waitFor(() => expect(f.mock.calls.length).toBe(n + 1));
  });
});
