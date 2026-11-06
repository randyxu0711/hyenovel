import { describe, it, expect, vi, beforeEach, afterEach, type MockInstance } from "vitest";
import { render, screen, fireEvent, waitFor, act, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { api, DashError, type Memory, type TurnMemory } from "../src/dash/api";
import Dash from "../src/dash/Dash";
import { ICON_NAMES } from "../src/dash/Icon";
import { setLang } from "../src/dash/i18n";
import Remember from "../src/dash/Remember";
import { userSeq } from "../src/dash/useTalk";
import { olive, hyena, buffalo, deer } from "./dash-fixtures";

const WORDS = "我不寫結局,真的";
const row = (id: number, scope: "author" | "work"): Memory => ({
  id, root: id, scope, slug: "s", title: "海", text: "x", quote: "x", session: "sid", seq: 3,
  valid_from: 1, learned_at: 1, invalidated_at: null,
});

let changed: ReturnType<typeof vi.fn>;
let remember: MockInstance<typeof api.remember>;
let archive: MockInstance<typeof api.archiveMemory>;

const mount = (initial: TurnMemory[] = []) =>
  render(<Remember slug="s" session="sid" seq={3} text={WORDS} initial={initial} onChange={changed} />);
const opener = () => screen.getByRole("button", { name: "記住" });
const box = () => screen.getByRole("textbox", { name: "記憶內容" }) as HTMLTextAreaElement;
const marks = (c: HTMLElement) => c.querySelectorAll(".chat-mem-mark");

function selectPart(from: number, to: number) {
  const node = screen.getByText(WORDS).firstChild!;
  const range = document.createRange();
  range.setStart(node, from); range.setEnd(node, to);
  document.getSelection()!.removeAllRanges(); document.getSelection()!.addRange(range);
  act(() => { document.dispatchEvent(new Event("selectionchange")); });
}

beforeEach(() => {
  setLang("zh-Hant");
  changed = vi.fn();
  remember = vi.spyOn(api, "remember").mockResolvedValue(row(7, "work"));
  archive = vi.spyOn(api, "archiveMemory").mockResolvedValue(undefined);
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.getSelection()!.removeAllRanges(); });

describe("Remember", () => {
  it("選了那則的部分文字,預設內容就是選取內容,來源引文也是", async () => {
    mount();
    selectPart(1, 5);
    fireEvent.click(opener());
    expect(box().value).toBe("不寫結局");
    fireEvent.click(screen.getByRole("button", { name: "記下" }));
    await waitFor(() => expect(remember).toHaveBeenCalledWith(
      { scope: "work", text: "不寫結局", slug: "s", session: "sid", seq: 3, quote: "不寫結局" }));
  });

  it("按下記住鈕不會讓選取消失", () => {
    mount();
    selectPart(1, 5);
    expect(fireEvent.mouseDown(opener())).toBe(false);
  });

  it("沒選字,預設內容是整則", () => {
    mount();
    fireEvent.click(opener());
    expect(box().value).toBe(WORDS);
  });

  it("改內容不改來源引文:送出的 quote 還是原話", async () => {
    mount();
    fireEvent.click(opener());
    fireEvent.change(box(), { target: { value: "作者不寫結局" } });
    fireEvent.click(screen.getByRole("button", { name: "記下" }));
    await waitFor(() => expect(remember.mock.calls[0][0]).toMatchObject({ text: "作者不寫結局", quote: WORDS }));
  });

  it("內容全空白不能送", () => {
    mount();
    fireEvent.click(opener());
    fireEvent.change(box(), { target: { value: "  " } });
    expect((screen.getByRole("button", { name: "記下" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("選寫到這篇 → scope work 帶 slug;寫到作者 → scope author 也帶 slug", async () => {
    mount();
    fireEvent.click(opener());
    expect(screen.getByRole("button", { name: "這篇" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "作者" }));
    remember.mockResolvedValue(row(8, "author"));
    fireEvent.click(screen.getByRole("button", { name: "記下" }));
    await waitFor(() => expect(remember.mock.calls[0][0]).toMatchObject({ scope: "author", slug: "s" }));
  });

  it("寫入後那則旁出記憶圖示和層名,按撤銷呼叫 archiveMemory 並恢復成可記住", async () => {
    const { container } = mount();
    fireEvent.click(opener());
    fireEvent.click(screen.getByRole("button", { name: "記下" }));
    await waitFor(() => expect(marks(container)).toHaveLength(1));
    expect(marks(container)[0].textContent).toContain("這篇");
    expect(marks(container)[0].querySelector("svg")).not.toBeNull();
    expect(changed).toHaveBeenLastCalledWith([{ id: 7, scope: "work" }]);
    expect(screen.queryByRole("textbox", { name: "記憶內容" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "撤銷" }));
    await waitFor(() => expect(archive).toHaveBeenCalledWith(7));
    await waitFor(() => expect(marks(container)).toHaveLength(0));
    expect(changed).toHaveBeenLastCalledWith([]);
    expect(opener()).toBeTruthy();
  });

  it("撤銷失敗:記號還在,顯示原因", async () => {
    archive.mockRejectedValue(new DashError(409, "memory-not-current"));
    const { container } = mount([{ id: 7, scope: "author" }]);
    fireEvent.click(screen.getByRole("button", { name: "撤銷" }));
    expect((await screen.findByRole("alert")).textContent).toContain("不是生效中");
    expect(marks(container)).toHaveLength(1);
  });

  it("den 回 memory-full,顯示對應文案,不出記憶圖示,寫到一半的字不丟", async () => {
    remember.mockRejectedValue(new DashError(422, "memory-full"));
    const { container } = mount();
    fireEvent.click(opener());
    fireEvent.change(box(), { target: { value: "改過的字" } });
    fireEvent.click(screen.getByRole("button", { name: "記下" }));
    expect((await screen.findByRole("alert")).textContent).toContain("滿了");
    expect(marks(container)).toHaveLength(0);
    expect(box().value).toBe("改過的字");
    expect(changed).not.toHaveBeenCalled();
  });

  it("兩個撤銷重疊時,先撤的不會復活", async () => {
    let finishA!: () => void, finishB!: () => void;
    archive.mockImplementationOnce(() => new Promise<void>(r => { finishA = r; }));
    archive.mockImplementationOnce(() => new Promise<void>(r => { finishB = r; }));
    const { container } = mount([{ id: 1, scope: "work" }, { id: 2, scope: "author" }]);
    const [undoA, undoB] = screen.getAllByRole("button", { name: "撤銷" });
    fireEvent.click(undoA);
    fireEvent.click(undoB);
    await act(async () => { finishA(); });
    await act(async () => { finishB(); });
    await waitFor(() => expect(marks(container)).toHaveLength(0));
    expect(changed).toHaveBeenLastCalledWith([]);
  });

  it("同一條連按撤銷只送一次", async () => {
    let finish!: () => void;
    archive.mockImplementationOnce(() => new Promise<void>(r => { finish = r; }));
    mount([{ id: 1, scope: "work" }]);
    const undo = screen.getByRole("button", { name: "撤銷" });
    fireEvent.click(undo);
    fireEvent.click(undo);
    await act(async () => { finish(); });
    expect(archive).toHaveBeenCalledTimes(1);
  });

  it("已記過的逐字重新載入後,旁邊就有記憶圖示", () => {
    const { container } = mount([{ id: 7, scope: "author" }]);
    expect(marks(container)).toHaveLength(1);
    expect(marks(container)[0].textContent).toContain("作者");
  });

  it("記憶圖示是專用的", () => {
    expect(ICON_NAMES).toContain("memory");
  });
});

describe("userSeq", () => {
  it("作者有說話 = 回覆 seq - 1", () => expect(userSeq("嗨", 5)).toBe(4));
  it("陪讀者先開口的那輪,作者發言沒有 seq", () => {
    expect(userSeq("", 0)).toBeUndefined();
    expect(userSeq("", 7)).toBeUndefined();
  });
});

describe("掛在對話裡", () => {
  const u = (seq: number | undefined, t: string, memories: TurnMemory[] = []) =>
    ({ seq, role: "user", text: t, ts: 1, character: null, quotes: [], spans: [], memories });
  const a = (seq: number, t: string) =>
    ({ seq, role: "assistant", text: t, ts: 1, character: "hyena", quotes: [], spans: [], memories: [] });
  const json = (b: unknown) => new Response(JSON.stringify(b), { status: 200 });
  const sse = (...evs: [string, unknown][]) => new Response(new ReadableStream({
    start(c) {
      const enc = new TextEncoder();
      for (const [event, data] of evs) c.enqueue(enc.encode(`data: ${JSON.stringify({ event, data })}\n\n`));
      c.close();
    },
  }));
  function mountDash(turns: object[]) {
    const rows = turns.length ? [{ session: "s1", started_at: 1, last_at: 2, turns: 1, character: "hyena", preview: "", version: 1, legacy: false }] : [];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const p = url.split("?")[0];
      if (p === "/api/themes") return json({ themes: [olive], default: "olive" });
      if (p === "/api/characters") return json({ characters: [hyena, buffalo, deer], default: "hyena" });
      if (p === "/api/works") return json({ works: [{ slug: "d1", title: "海", version: 1, chars: 4 }] });
      if (p === "/api/works/d1") return json({ slug: "d1", title: "海", version: 1, versions: [1], text: "第一段。", state: "ready", job_id: null, notes_ready: false });
      if (p === "/api/works/d1/map") return json({ version: 1, analysis_version: null, notes_version: null, beats: [], motifs: [], notes: null });
      if (p === "/api/works/d1/sessions") return json({ sessions: rows });
      if (p.startsWith("/api/discuss/")) return sse(
        ["message", { role: "assistant", text: "回覆", session_id: "s1", seq: 1, character: "hyena", spans: [] }],
        ["done", { ok: true, session_id: "s1" }]);
      if (p === "/api/sessions/s1") return json({ session: "s1", slug: "d1", title: "海", turns, legacy: false, version: 1 });
      return json({ sessions: [] });
    }));
    return render(<MemoryRouter initialEntries={["/w/d1"]}><Routes><Route path="/w/:slug" element={<Dash />} /></Routes></MemoryRouter>);
  }

  it("串流剛結束的作者發言帶 seq = 回覆 seq - 1", async () => {
    mountDash([]);
    fireEvent.change(await screen.findByLabelText("對話輸入"), { target: { value: "我說的話" } });
    fireEvent.click(screen.getByRole("button", { name: "送出" }));
    await screen.findByText("回覆");
    fireEvent.click(within(screen.getByRole("log")).getByRole("button", { name: "記住" }));
    fireEvent.click(screen.getByRole("button", { name: "記下" }));
    await waitFor(() => expect(remember.mock.calls[0][0]).toMatchObject({ session: "s1", seq: 0, quote: "我說的話" }));
  });

  it("沒有 seq 的作者發言不出記住鈕", async () => {
    mountDash([u(undefined, "舊的話"), a(1, "回覆")]);
    const log = within(await screen.findByRole("log"));
    await log.findByText("舊的話");
    expect(log.queryByRole("button", { name: "記住" })).toBeNull();
  });

  it("assistant 回覆沒有記住鈕", async () => {
    mountDash([u(0, "我的話"), a(1, "回覆")]);
    const log = within(await screen.findByRole("log"));
    await log.findByText("回覆");
    expect(log.getAllByRole("button", { name: "記住" })).toHaveLength(1);
  });

  it("重新載入的逐字帶著 memories", async () => {
    mountDash([u(0, "我的話", [{ id: 3, scope: "work" }]), a(1, "回覆")]);
    const log = await screen.findByRole("log");
    await within(log).findByText("回覆");
    expect(marks(log)).toHaveLength(1);
  });

  it("在對話裡撤銷,記號就消失", async () => {
    mountDash([u(0, "我的話", [{ id: 3, scope: "work" }]), a(1, "回覆")]);
    const log = await screen.findByRole("log");
    await within(log).findByText("回覆");
    fireEvent.click(within(log).getByRole("button", { name: "撤銷" }));
    await waitFor(() => expect(archive).toHaveBeenCalledWith(3));
    await waitFor(() => expect(marks(log)).toHaveLength(0));
  });
});
