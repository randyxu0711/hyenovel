import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, act, fireEvent } from "@testing-library/react";
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
      <Reader slug="d1" onQuote={onQuote} />
    </CharactersProvider>);
  await screen.findByText("海");
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
    render(<CharactersProvider value={makeCharacters([hyena], "hyena")}><Reader slug="zz" onQuote={vi.fn()} /></CharactersProvider>);
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "找不到這篇作品。");
  });
});
