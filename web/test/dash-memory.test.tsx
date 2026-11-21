import { describe, it, expect, vi, beforeEach, afterEach, type MockInstance } from "vitest";
import { render, screen, fireEvent, waitFor, within, act } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { api, DashError, type Memory, type MemoryList } from "../src/dash/api";
import { setLang } from "../src/dash/i18n";
import MemoryPage from "../src/dash/MemoryPage";

const CAPS = { author: 800, work: 600 };
const mem = (over: Partial<Memory>): Memory => ({
  id: 1, root: over.id ?? 1, scope: "author", slug: null, title: null, text: "記", quote: null, session: null, seq: null,
  valid_from: 1, learned_at: 1, invalidated_at: null, ...over,
});
const list = (...memories: Memory[]): MemoryList => ({ memories, caps: CAPS });

let memories: MockInstance<typeof api.memories>;
let edit: MockInstance<typeof api.editMemory>;
let archive: MockInstance<typeof api.archiveMemory>;
let revert: MockInstance<typeof api.revertMemory>;
let remember: MockInstance<typeof api.remember>;

function Where() { const l = useLocation(); return <output data-testid="loc">{l.pathname}{l.search}</output>; }
let works: MockInstance<typeof api.memoryWorks>;
const mount = async () => {
  const r = render(<MemoryRouter initialEntries={["/settings"]}><Where /><MemoryPage /></MemoryRouter>);
  await waitFor(() => expect(works).toHaveBeenCalled());
  await act(async () => {});
  const rest = document.querySelector<HTMLButtonElement>(".dash-mg-rest");
  if (rest) fireEvent.click(rest);
  await act(async () => {});
  document.querySelectorAll<HTMLButtonElement>(".dash-mg-head[aria-expanded=false]").forEach(b => fireEvent.click(b));
  return r;
};
const addOpen = (group = "關於我") => {
  const btn = within(screen.getByRole("group", { name: group })).queryByRole("button", { name: "手動新增" });
  if (btn) fireEvent.click(btn);
};
const groupOf = (name: string) => screen.findByRole("group", { name });

beforeEach(() => {
  localStorage.clear();
  setLang("zh-Hant");
  memories = vi.spyOn(api, "memories").mockResolvedValue(list());
  edit = vi.spyOn(api, "editMemory").mockResolvedValue(mem({ id: 2, root: 1 }));
  archive = vi.spyOn(api, "archiveMemory").mockResolvedValue(undefined);
  revert = vi.spyOn(api, "revertMemory").mockResolvedValue(mem({ id: 3, root: 1 }));
  remember = vi.spyOn(api, "remember").mockResolvedValue(mem({ id: 9 }));
  vi.spyOn(api, "works").mockResolvedValue([
    { slug: "d1", title: "海", version: 1, chars: 4, updated_at: 1, state: "ready" },
    { slug: "d2", title: "山", version: 1, chars: 4, updated_at: 1, state: "ready" },
  ]);
  vi.spyOn(api, "priorEnabled").mockResolvedValue(true);
  vi.spyOn(api, "candidates").mockResolvedValue([]);
  works = vi.spyOn(api, "memoryWorks").mockResolvedValue([
    { slug: "d1", title: "海", digests: [], threads: [] },
    { slug: "d2", title: "山", digests: [], threads: [] },
  ]);
});
afterEach(() => vi.restoreAllMocks());

describe("MemoryPage", () => {
  it("頁底:建議記憶切到關閉 → 送 setSuggestEnabled(false),待確認區消失", async () => {
    vi.spyOn(api, "suggestEnabled").mockResolvedValue(true);
    const set = vi.spyOn(api, "setSuggestEnabled").mockResolvedValue(undefined);
    const cands = vi.spyOn(api, "candidates").mockResolvedValue([{ id: 7, text: "甲", quote: "甲", scope: "author",
      session: "s1", seq: 0, slug: null, title: null, at: 1 }]);
    await mount();
    await screen.findByRole("region", { name: "待確認" });
    cands.mockResolvedValue([]);
    const seg = screen.getByRole("group", { name: "建議記憶" });
    expect(within(seg).getByRole("button", { name: "逐條確認" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(within(seg).getByRole("button", { name: "關閉" }));
    await waitFor(() => expect(set).toHaveBeenCalledWith(false));
    await waitFor(() => expect(screen.queryByRole("region", { name: "待確認" })).toBeNull());
  });
  it("頁底:已封存清單在開關同一列", async () => {
    memories.mockResolvedValue(list(mem({ id: 1, text: "甲", invalidated_at: 2 })));
    await mount();
    const foot = document.querySelector(".dash-mem-foot") as HTMLElement;
    expect(within(foot).getByRole("button", { name: "已封存 1 條" })).toBeTruthy();
    expect(within(foot).getByRole("group", { name: "新對話帶入前次摘要" })).toBeTruthy();
  });
  it("待確認區在最上面;存入後重新載入記憶", async () => {
    vi.spyOn(api, "candidates").mockResolvedValue([{ id: 7, text: "先有最後一句", quote: "我都是先有最後一句", scope: "author",
      session: "s1", seq: 0, slug: "d1", title: "海", at: 1 }]);
    vi.spyOn(api, "saveCandidate").mockResolvedValue(mem({ id: 7 }));
    await mount();
    const s = await screen.findByRole("region", { name: "待確認" });
    const before = memories.mock.calls.length;
    fireEvent.click(within(s).getByRole("button", { name: "存入關於我" }));
    await waitFor(() => expect(memories.mock.calls.length).toBe(before + 1));
  });
  it("頁底開關:顯示目前設定,點關閉呼叫 setPriorEnabled(false)", async () => {
    const set = vi.spyOn(api, "setPriorEnabled").mockResolvedValue(undefined);
    await mount();
    const seg = await screen.findByRole("group", { name: "新對話帶入前次摘要" });
    expect(within(seg).getByRole("button", { name: "開啟" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(within(seg).getByRole("button", { name: "關閉" }));
    await waitFor(() => expect(set).toHaveBeenCalledWith(false));
    await waitFor(() => expect(within(seg).getByRole("button", { name: "關閉" }).getAttribute("aria-pressed")).toBe("true"));
  });
  it("頁底開關:讀不到設定就不顯示", async () => {
    vi.spyOn(api, "priorEnabled").mockRejectedValue(new DashError(0, "den-down"));
    await mount();
    await screen.findByRole("textbox", { name: "新增記憶" });
    expect(screen.queryByRole("group", { name: "新對話帶入前次摘要" })).toBeNull();
  });
  it("生效中的記憶依作者、各篇分組,顯示已用字數/上限", async () => {
    memories.mockResolvedValue(list(
      mem({ id: 1, text: "😀寫" }),
      mem({ id: 2, scope: "work", slug: "d1", title: "海", text: "這篇的事" }),
      mem({ id: 3, scope: "work", slug: "d2", title: null, text: "別篇" }),
    ));
    await mount();
    const author = await groupOf("關於我");
    expect(within(author).getByText("😀寫")).toBeTruthy();
    expect(within(author).getByText("2/800")).toBeTruthy();
    const sea = screen.getByRole("group", { name: "海" });
    expect(within(sea).getByText("這篇的事")).toBeTruthy();
    expect(within(sea).getByText("4/600")).toBeTruthy();
    expect(within(screen.getByRole("group", { name: "山" })).getByText("別篇")).toBeTruthy();
  });

  it("有來源的顯示原話引文,連結圖示跳到 /作品路由?s=<session>", async () => {
    memories.mockResolvedValue(list(mem({ text: "內容", quote: "原話", slug: "d 1", session: "s/1", seq: 0 })));
    await mount();
    expect((await screen.findByText("原話")).tagName).toBe("BLOCKQUOTE");
    fireEvent.click(screen.getByRole("link", { name: "出自對話" }));
    expect(screen.getByTestId("loc").textContent).toBe("/w/d%201?s=s%2F1");
  });

  it("記的就是整句原話時不重複列,改標「出自對話」,一樣能跳回去", async () => {
    memories.mockResolvedValue(list(mem({ text: "同一句", quote: "同一句 ", slug: "d1", session: "s1", seq: 0 })));
    await mount();
    expect(await screen.findAllByText("同一句")).toHaveLength(1);
    fireEvent.click(screen.getByRole("link", { name: "出自對話" }));
    expect(screen.getByTestId("loc").textContent).toBe("/w/d1?s=s1");
  });

  it("沒綁作品的局記下的,連回那一局", async () => {
    memories.mockResolvedValue(list(mem({ text: "在聊天說的", quote: "在聊天說的", slug: null, session: "c/9", seq: 0 })));
    await mount();
    fireEvent.click(await screen.findByRole("link", { name: "出自對話" }));
    expect(screen.getByTestId("loc").textContent).toBe("/c/c%2F9");
  });

  it("沒有來源的沒有連結也沒有引文", async () => {
    memories.mockResolvedValue(list(mem({ text: "手打的" })));
    await mount();
    const li = (await screen.findByText("手打的")).closest("li") as HTMLElement;
    expect(li.querySelector("blockquote")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("編輯送 editMemory,成功後列表換成新列", async () => {
    memories.mockResolvedValueOnce(list(mem({ id: 1, text: "舊" })));
    memories.mockResolvedValueOnce(list(mem({ id: 1, text: "舊", invalidated_at: 2 }), mem({ id: 2, root: 1, text: "新" })));
    await mount();
    fireEvent.click(await screen.findByRole("button", { name: "編輯" }));
    fireEvent.change(screen.getByRole("textbox", { name: "記憶內容" }), { target: { value: "新" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));
    await waitFor(() => expect(edit).toHaveBeenCalledWith(1, "新"));
    expect(await screen.findByText("新")).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: "記憶內容" })).toBeNull();
  });

  it("封存後移到收合的封存區;按拉回送 revertMemory", async () => {
    memories.mockResolvedValueOnce(list(mem({ id: 1, text: "甲" })));
    memories.mockResolvedValue(list(mem({ id: 1, text: "甲", invalidated_at: 2 })));
    await mount();
    fireEvent.click(await screen.findByRole("button", { name: "封存" }));
    await waitFor(() => expect(archive).toHaveBeenCalledWith(1));
    const toggle = await screen.findByRole("button", { name: "已封存 1 條" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("甲")).toBeNull();
    fireEvent.click(toggle);
    expect(screen.getByText("甲")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "還原" }));
    await waitFor(() => expect(revert).toHaveBeenCalledWith(1));
  });

  it("封存再編輯過的 chain 拉回的是最後一版", async () => {
    memories.mockResolvedValue(list(
      mem({ id: 1, text: "第一版", invalidated_at: 2 }),
      mem({ id: 2, root: 1, text: "第二版", invalidated_at: 3 }),
    ));
    await mount();
    fireEvent.click(await screen.findByRole("button", { name: "已封存 1 條" }));
    fireEvent.click(screen.getByRole("button", { name: "還原" }));
    await waitFor(() => expect(revert).toHaveBeenCalledWith(2));
  });

  it("歷史版本可展開,按回到這版送 revertMemory", async () => {
    memories.mockResolvedValue(list(
      mem({ id: 1, text: "第一版", invalidated_at: 2 }),
      mem({ id: 2, root: 1, text: "第二版" }),
    ));
    await mount();
    await screen.findByText("第二版");
    expect(screen.queryByText("第一版")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "歷史版本" }));
    expect(screen.getByText("第一版")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "還原" }));
    await waitFor(() => expect(revert).toHaveBeenCalledWith(1));
  });

  it("只有一版沒有歷史鈕", async () => {
    memories.mockResolvedValue(list(mem({ text: "唯一" })));
    await mount();
    await screen.findByText("唯一");
    expect(screen.queryByRole("button", { name: "歷史版本" })).toBeNull();
  });

  it("手動新增:不帶 session/seq/quote,層別跟著群組;成功後收起", async () => {
    await mount();
    addOpen();
    fireEvent.change(screen.getByRole("textbox", { name: "新增記憶" }), { target: { value: "手打" } });
    fireEvent.click(screen.getByRole("button", { name: "新增" }));
    await waitFor(() => expect(remember).toHaveBeenCalledWith({ scope: "author", text: "手打" }));
    await waitFor(() => expect(memories).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("textbox", { name: "新增記憶" })).toBeNull();
  });

  it("memory-full 顯示對應文案,編輯中的文字不丟", async () => {
    memories.mockResolvedValue(list(mem({ id: 1, text: "舊" })));
    edit.mockRejectedValue(new DashError(422, "memory-full"));
    await mount();
    fireEvent.click(await screen.findByRole("button", { name: "編輯" }));
    fireEvent.change(screen.getByRole("textbox", { name: "記憶內容" }), { target: { value: "很長的字" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));
    expect((await screen.findByRole("alert")).textContent).toContain("滿了");
    expect((screen.getByRole("textbox", { name: "記憶內容" }) as HTMLTextAreaElement).value).toBe("很長的字");
  });

  it("新增遇到 memory-full,打的字不丟", async () => {
    remember.mockRejectedValue(new DashError(422, "memory-full"));
    await mount();
    addOpen();
    fireEvent.change(screen.getByRole("textbox", { name: "新增記憶" }), { target: { value: "很長" } });
    fireEvent.click(screen.getByRole("button", { name: "新增" }));
    expect((await screen.findByRole("alert")).textContent).toContain("滿了");
    expect((screen.getByRole("textbox", { name: "新增記憶" }) as HTMLTextAreaElement).value).toBe("很長");
  });

  it("新增連按兩次只寫一條", async () => {
    let finish!: (m: Memory) => void;
    remember.mockImplementationOnce(() => new Promise<Memory>(r => { finish = r; }));
    await mount();
    addOpen();
    fireEvent.change(screen.getByRole("textbox", { name: "新增記憶" }), { target: { value: "一次" } });
    const add = screen.getByRole("button", { name: "新增" });
    fireEvent.click(add);
    fireEvent.click(add);
    finish(mem({ id: 9 }));
    await waitFor(() => expect(memories).toHaveBeenCalledTimes(2));
    expect(remember).toHaveBeenCalledTimes(1);
  });

  it("寫入成功但重新載入失敗:不當成寫入失敗,文字清掉、編輯收起,顯示原因", async () => {
    memories.mockResolvedValueOnce(list(mem({ id: 1, text: "舊" })));
    memories.mockRejectedValue(new DashError(0, "den-down"));
    await mount();
    fireEvent.click(await screen.findByRole("button", { name: "編輯" }));
    fireEvent.change(screen.getByRole("textbox", { name: "記憶內容" }), { target: { value: "新" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));
    expect((await screen.findByRole("alert")).textContent).toContain("den");
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "記憶內容" })).toBeNull());
    addOpen();
    fireEvent.change(screen.getByRole("textbox", { name: "新增記憶" }), { target: { value: "手打" } });
    fireEvent.click(screen.getByRole("button", { name: "新增" }));
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "新增記憶" })).toBeNull());
  });

  it("載入失敗顯示原因", async () => {
    memories.mockRejectedValue(new DashError(0, "den-down"));
    await mount();
    expect((await screen.findByRole("alert")).textContent).toContain("den");
  });

  it("沒有任何記憶時:關於我仍在,新增框直接打開", async () => {
    await mount();
    const me = screen.getByRole("group", { name: "關於我" });
    expect(within(me).getByRole("textbox", { name: "新增記憶" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /已封存/ })).toBeNull();
  });

});
