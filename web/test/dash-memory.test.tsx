import { describe, it, expect, vi, beforeEach, afterEach, type MockInstance } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
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
const mount = () => render(<MemoryRouter initialEntries={["/settings"]}><Where /><MemoryPage /></MemoryRouter>);
const groupOf = (name: string) => screen.findByRole("group", { name });

beforeEach(() => {
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
});
afterEach(() => vi.restoreAllMocks());

describe("MemoryPage", () => {
  it("生效中的記憶依作者、各篇分組,顯示已用字數/上限", async () => {
    memories.mockResolvedValue(list(
      mem({ id: 1, text: "😀寫" }),
      mem({ id: 2, scope: "work", slug: "d1", title: "海", text: "這篇的事" }),
      mem({ id: 3, scope: "work", slug: "d2", title: null, text: "別篇" }),
    ));
    mount();
    const author = await groupOf("作者");
    expect(within(author).getByText("😀寫")).toBeTruthy();
    expect(within(author).getByText("2/800")).toBeTruthy();
    const sea = screen.getByRole("group", { name: "海" });
    expect(within(sea).getByText("這篇的事")).toBeTruthy();
    expect(within(sea).getByText("4/600")).toBeTruthy();
    expect(within(screen.getByRole("group", { name: "d2" })).getByText("別篇")).toBeTruthy();
  });

  it("有來源的顯示原話,點了跳到 /作品路由?s=<session>", async () => {
    memories.mockResolvedValue(list(mem({ text: "內容", quote: "原話", slug: "d 1", session: "s/1", seq: 0 })));
    mount();
    fireEvent.click(await screen.findByRole("link", { name: /原話/ }));
    expect(screen.getByTestId("loc").textContent).toBe("/w/d%201?s=s%2F1");
    expect(screen.queryByText("手寫")).toBeNull();
  });

  it("沒有來源的顯示手寫標記", async () => {
    memories.mockResolvedValue(list(mem({ text: "手打的" })));
    mount();
    await screen.findByText("手打的");
    expect(screen.getByText("手寫")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("編輯送 editMemory,成功後列表換成新列", async () => {
    memories.mockResolvedValueOnce(list(mem({ id: 1, text: "舊" })));
    memories.mockResolvedValueOnce(list(mem({ id: 1, text: "舊", invalidated_at: 2 }), mem({ id: 2, root: 1, text: "新" })));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "改" }));
    fireEvent.change(screen.getByRole("textbox", { name: "記憶內容" }), { target: { value: "新" } });
    fireEvent.click(screen.getByRole("button", { name: "存" }));
    await waitFor(() => expect(edit).toHaveBeenCalledWith(1, "新"));
    expect(await screen.findByText("新")).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: "記憶內容" })).toBeNull();
  });

  it("封存後移到收合的封存區;按拉回送 revertMemory", async () => {
    memories.mockResolvedValueOnce(list(mem({ id: 1, text: "甲" })));
    memories.mockResolvedValue(list(mem({ id: 1, text: "甲", invalidated_at: 2 })));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "封存" }));
    await waitFor(() => expect(archive).toHaveBeenCalledWith(1));
    const toggle = await screen.findByRole("button", { name: "已封存 1 條" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("甲")).toBeNull();
    fireEvent.click(toggle);
    expect(screen.getByText("甲")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "拉回" }));
    await waitFor(() => expect(revert).toHaveBeenCalledWith(1));
  });

  it("封存再編輯過的 chain 拉回的是最後一版", async () => {
    memories.mockResolvedValue(list(
      mem({ id: 1, text: "第一版", invalidated_at: 2 }),
      mem({ id: 2, root: 1, text: "第二版", invalidated_at: 3 }),
    ));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "已封存 1 條" }));
    fireEvent.click(screen.getByRole("button", { name: "拉回" }));
    await waitFor(() => expect(revert).toHaveBeenCalledWith(2));
  });

  it("歷史版本可展開,按回到這版送 revertMemory", async () => {
    memories.mockResolvedValue(list(
      mem({ id: 1, text: "第一版", invalidated_at: 2 }),
      mem({ id: 2, root: 1, text: "第二版" }),
    ));
    mount();
    await screen.findByText("第二版");
    expect(screen.queryByText("第一版")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "歷史版本" }));
    expect(screen.getByText("第一版")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "回到這版" }));
    await waitFor(() => expect(revert).toHaveBeenCalledWith(1));
  });

  it("只有一版沒有歷史鈕", async () => {
    memories.mockResolvedValue(list(mem({ text: "唯一" })));
    mount();
    await screen.findByText("唯一");
    expect(screen.queryByRole("button", { name: "歷史版本" })).toBeNull();
  });

  it("手打新增:不帶 session/seq/quote;寫到這篇要選作品", async () => {
    mount();
    const box = await screen.findByRole("textbox", { name: "新增記憶" });
    const add = screen.getByRole("button", { name: "新增" }) as HTMLButtonElement;
    fireEvent.change(box, { target: { value: "手打" } });
    fireEvent.click(add);
    await waitFor(() => expect(remember).toHaveBeenCalledWith({ scope: "author", text: "手打" }));
    await waitFor(() => expect(memories).toHaveBeenCalledTimes(2));
    expect((screen.getByRole("textbox", { name: "新增記憶" }) as HTMLTextAreaElement).value).toBe("");

    remember.mockClear();
    fireEvent.change(screen.getByRole("textbox", { name: "新增記憶" }), { target: { value: "關於海" } });
    fireEvent.click(screen.getByRole("button", { name: "這篇" }));
    expect((screen.getByRole("button", { name: "新增" }) as HTMLButtonElement).disabled).toBe(true);
    const pick = await screen.findByRole("combobox", { name: "哪一篇" });
    await within(pick).findByRole("option", { name: "海" });
    fireEvent.change(pick, { target: { value: "d1" } });
    fireEvent.click(screen.getByRole("button", { name: "新增" }));
    await waitFor(() => expect(remember).toHaveBeenCalledWith({ scope: "work", text: "關於海", slug: "d1" }));
  });

  it("memory-full 顯示對應文案,編輯中的文字不丟", async () => {
    memories.mockResolvedValue(list(mem({ id: 1, text: "舊" })));
    edit.mockRejectedValue(new DashError(422, "memory-full"));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "改" }));
    fireEvent.change(screen.getByRole("textbox", { name: "記憶內容" }), { target: { value: "很長的字" } });
    fireEvent.click(screen.getByRole("button", { name: "存" }));
    expect((await screen.findByRole("alert")).textContent).toContain("滿了");
    expect((screen.getByRole("textbox", { name: "記憶內容" }) as HTMLTextAreaElement).value).toBe("很長的字");
  });

  it("新增遇到 memory-full,打的字不丟", async () => {
    remember.mockRejectedValue(new DashError(422, "memory-full"));
    mount();
    fireEvent.change(await screen.findByRole("textbox", { name: "新增記憶" }), { target: { value: "很長" } });
    fireEvent.click(screen.getByRole("button", { name: "新增" }));
    expect((await screen.findByRole("alert")).textContent).toContain("滿了");
    expect((screen.getByRole("textbox", { name: "新增記憶" }) as HTMLTextAreaElement).value).toBe("很長");
  });

  it("新增連按兩次只寫一條", async () => {
    let finish!: (m: Memory) => void;
    remember.mockImplementationOnce(() => new Promise<Memory>(r => { finish = r; }));
    mount();
    fireEvent.change(await screen.findByRole("textbox", { name: "新增記憶" }), { target: { value: "一次" } });
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
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "改" }));
    fireEvent.change(screen.getByRole("textbox", { name: "記憶內容" }), { target: { value: "新" } });
    fireEvent.click(screen.getByRole("button", { name: "存" }));
    expect((await screen.findByRole("alert")).textContent).toContain("den");
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "記憶內容" })).toBeNull());
    fireEvent.change(screen.getByRole("textbox", { name: "新增記憶" }), { target: { value: "手打" } });
    fireEvent.click(screen.getByRole("button", { name: "新增" }));
    await waitFor(() => expect((screen.getByRole("textbox", { name: "新增記憶" }) as HTMLTextAreaElement).value).toBe(""));
  });

  it("載入失敗顯示原因", async () => {
    memories.mockRejectedValue(new DashError(0, "den-down"));
    mount();
    expect((await screen.findByRole("alert")).textContent).toContain("den");
  });

  it("沒有任何記憶時只顯示新增", async () => {
    mount();
    await screen.findByRole("textbox", { name: "新增記憶" });
    await waitFor(() => expect(memories).toHaveBeenCalled());
    expect(screen.queryByRole("group", { name: "作者" })).toBeNull();
    expect(screen.queryByRole("button", { name: /已封存/ })).toBeNull();
  });
});
