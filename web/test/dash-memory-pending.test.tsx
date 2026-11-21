import { describe, it, expect, vi, beforeEach, afterEach, type MockInstance } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { api, DashError, type Memory, type MemoryCandidate } from "../src/dash/api";
import { setLang } from "../src/dash/i18n";
import MemoryPending from "../src/dash/MemoryPending";

const cand = (over: Partial<MemoryCandidate>): MemoryCandidate => ({
  id: 1, text: "寫作時先有最後一句", quote: "我都是先有最後一句", scope: "author", session: "s1", seq: 0,
  slug: "d1", title: "海", at: Date.now() / 1000, ...over,
});
const saved = { id: 50, root: 50 } as Memory;

let candidates: MockInstance<typeof api.candidates>;
let save: MockInstance<typeof api.saveCandidate>;
let skip: MockInstance<typeof api.skipCandidate>;
let undo: MockInstance<typeof api.undoCandidate>;
let onChange: ReturnType<typeof vi.fn<() => void>>;
let onCount: ReturnType<typeof vi.fn<(n: number) => void>>;
let onSaved: ReturnType<typeof vi.fn>;
let onGoto: ReturnType<typeof vi.fn>;

const mount = (focus = false) => render(<MemoryPending onChange={onChange} onCount={onCount} onSaved={onSaved} onGoto={onGoto} focus={focus} />);
const section = () => screen.findByRole("region", { name: "待確認" });
const item = async (text: string) => (await screen.findByText(text)).closest("li") as HTMLElement;

beforeEach(() => {
  setLang("zh-Hant");
  onChange = vi.fn(); onCount = vi.fn(); onSaved = vi.fn(); onGoto = vi.fn();
  candidates = vi.spyOn(api, "candidates").mockResolvedValue([cand({})]);
  save = vi.spyOn(api, "saveCandidate").mockResolvedValue(saved);
  skip = vi.spyOn(api, "skipCandidate").mockResolvedValue(undefined);
  undo = vi.spyOn(api, "undoCandidate").mockResolvedValue(undefined);
});
afterEach(() => vi.restoreAllMocks());

describe("MemoryPending", () => {
  it("pending section hidden when no candidates", async () => {
    candidates.mockResolvedValue([]);
    const r = mount();
    await waitFor(() => expect(onCount).toHaveBeenCalledWith(0));
    expect(r.container.textContent).toBe("");
  });

  it("shows count, quote and source", async () => {
    mount();
    const s = await section();
    expect(within(s).getByRole("heading").textContent).toBe("待確認 1");
    const li = within(s).getByText("寫作時先有最後一句").closest("li") as HTMLElement;
    expect(within(li).getByText("〈海〉")).toBeTruthy();
    expect(li.querySelector("blockquote")?.textContent).toBe("我都是先有最後一句");
  });

  it("suggested layer button comes first", async () => {
    candidates.mockResolvedValue([cand({ scope: "work" })]);
    mount();
    const btns = within(await item("寫作時先有最後一句")).getAllByRole("button");
    expect(btns.map(b => b.textContent)).toEqual(["存入本篇", "存入關於我", "略過", ""]);
    expect(btns[0].className).toContain("yes");
  });

  it("chat-only candidate offers only author", async () => {
    candidates.mockResolvedValue([cand({ slug: null, title: null })]);
    mount();
    const li = await item("寫作時先有最後一句");
    expect(within(li).queryByRole("button", { name: "存入本篇" })).toBeNull();
    expect(within(li).getByText(/未綁定作品的對話/)).toBeTruthy();
  });

  it("save then undo restores candidate", async () => {
    mount();
    fireEvent.click(within(await item("寫作時先有最後一句")).getByRole("button", { name: "存入關於我" }));
    await waitFor(() => expect(save).toHaveBeenCalledWith(1, "author", undefined));
    const receipt = (await screen.findByRole("button", { name: "關於我" })).closest("li") as HTMLElement;
    expect(receipt.textContent).toContain("寫作時先有最後一句");
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onSaved).toHaveBeenCalledWith({ group: "", memory: 50 });
    fireEvent.click(screen.getByRole("button", { name: "復原" }));
    await waitFor(() => expect(undo).toHaveBeenCalledWith(1));
    expect(await screen.findByRole("button", { name: "存入關於我" })).toBeTruthy();
    expect(onChange).toHaveBeenCalledTimes(2);
  });

  it("skip then undo", async () => {
    mount();
    fireEvent.click(within(await item("寫作時先有最後一句")).getByRole("button", { name: "略過" }));
    await waitFor(() => expect(skip).toHaveBeenCalledWith(1));
    expect(await screen.findByText("已略過")).toBeTruthy();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("edit then save sends text", async () => {
    mount();
    const li = await item("寫作時先有最後一句");
    fireEvent.click(within(li).getByRole("button", { name: "編輯" }));
    fireEvent.change(within(li).getByRole("textbox"), { target: { value: "改過的" } });
    fireEvent.click(within(li).getByRole("button", { name: "存入關於我" }));
    await waitFor(() => expect(save).toHaveBeenCalledWith(1, "author", "改過的"));
  });

  it("older candidates collapsed beyond five", async () => {
    candidates.mockResolvedValue(Array.from({ length: 7 }, (_, i) => cand({ id: i + 1, text: `候選${i + 1}` })));
    mount();
    await screen.findByText("候選5");
    expect(screen.queryByText("候選6")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /較早 2 條/ }));
    expect(screen.getByText("候選7")).toBeTruthy();
  });

  it("undo refused as gone drops the receipt", async () => {
    undo.mockRejectedValue(new DashError(404, "unknown-memory-candidate"));
    mount();
    fireEvent.click(within(await item("寫作時先有最後一句")).getByRole("button", { name: "略過" }));
    fireEvent.click(await screen.findByRole("button", { name: "復原" }));
    await waitFor(() => expect(undo).toHaveBeenCalledWith(1));
    await waitFor(() => expect(screen.queryByRole("button", { name: "復原" })).toBeNull());
    expect(screen.queryByText("寫作時先有最後一句")).toBeNull();
  });

  it("undo after edit shows error", async () => {
    undo.mockRejectedValue(new DashError(409, "memory-not-current"));
    mount();
    fireEvent.click(within(await item("寫作時先有最後一句")).getByRole("button", { name: "存入關於我" }));
    fireEvent.click(await screen.findByRole("button", { name: "復原" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("button", { name: "關於我" })).toBeTruthy();
  });

  it("reports remaining count", async () => {
    candidates.mockResolvedValue([cand({ id: 1, text: "甲" }), cand({ id: 2, text: "乙" })]);
    mount();
    await waitFor(() => expect(onCount).toHaveBeenLastCalledWith(2));
    fireEvent.click(within(await item("甲")).getByRole("button", { name: "略過" }));
    await waitFor(() => expect(onCount).toHaveBeenLastCalledWith(1));
  });

  it("quote equal to text is not repeated", async () => {
    candidates.mockResolvedValue([cand({ quote: "寫作時先有最後一句 " })]);
    mount();
    const li = await item("寫作時先有最後一句");
    expect(li.querySelector("blockquote")).toBeNull();
  });

  it("done slips leave the list and older ones fill in", async () => {
    candidates.mockResolvedValue(Array.from({ length: 7 }, (_, i) => cand({ id: i + 1, text: `候選${i + 1}` })));
    mount();
    fireEvent.click(within(await item("候選1")).getByRole("button", { name: "略過" }));
    expect(await screen.findByText("候選6")).toBeTruthy();
    expect(screen.queryByText("候選7")).toBeNull();
    expect(screen.getByRole("button", { name: /較早 1 條/ })).toBeTruthy();
    const receipts = document.querySelector(".dash-pend-receipts") as HTMLElement;
    expect(within(receipts).getByText("候選1")).toBeTruthy();
    expect(within(receipts).getByText("已略過")).toBeTruthy();
  });

  it("receipt link goes to the work group", async () => {
    candidates.mockResolvedValue([cand({ scope: "work" })]);
    mount();
    fireEvent.click(within(await item("寫作時先有最後一句")).getByRole("button", { name: "存入本篇" }));
    fireEvent.click(await screen.findByRole("button", { name: "〈海〉" }));
    expect(onGoto).toHaveBeenCalledWith({ group: "d1", memory: 50 });
  });

  it("editing: Enter saves to the first layer, Esc cancels", async () => {
    candidates.mockResolvedValue([cand({ scope: "work" })]);
    mount();
    const li = await item("寫作時先有最後一句");
    fireEvent.click(within(li).getByRole("button", { name: "編輯" }));
    fireEvent.keyDown(within(li).getByRole("textbox"), { key: "Escape" });
    expect(within(li).queryByRole("textbox")).toBeNull();
    fireEvent.click(within(li).getByRole("button", { name: "編輯" }));
    const box = within(li).getByRole("textbox");
    fireEvent.change(box, { target: { value: "已編輯" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(save).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Enter" });
    await waitFor(() => expect(save).toHaveBeenCalledWith(1, "work", "已編輯"));
  });

  it("focus puts the first slip's main button in focus", async () => {
    mount(true);
    const btn = within(await item("寫作時先有最後一句")).getByRole("button", { name: "存入關於我" });
    await waitFor(() => expect(document.activeElement).toBe(btn));
  });
});
