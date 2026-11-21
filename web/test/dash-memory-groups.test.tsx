import { describe, it, expect, vi, beforeEach, afterEach, type MockInstance } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { api, type Memory, type MemoryList, type WorkOverview } from "../src/dash/api";
import { setLang } from "../src/dash/i18n";
import MemoryPage from "../src/dash/MemoryPage";

const now = Date.now() / 1000;
const mem = (over: Partial<Memory>): Memory => ({
  id: 1, root: over.id ?? 1, scope: "author", slug: null, title: null, text: "記", quote: null, session: null, seq: null,
  valid_from: 1, learned_at: 1, invalidated_at: null, ...over,
});
const list = (...memories: Memory[]): MemoryList => ({ memories, caps: { author: 800, work: 600 } });
const sea = (over: Partial<WorkOverview> = {}): WorkOverview => ({
  slug: "d1", title: "海",
  digests: [
    { id: 31, session: "s-a", at: now - 86400, text: "聊了結尾的嘻。", edited: false, versions: 2 },
    { id: 32, session: "s-b", at: now - 2 * 86400, text: "海豚那段。", edited: false, versions: 1 },
    { id: 33, session: "s-c", at: now - 3 * 86400, text: "初讀。", edited: false, versions: 1 },
  ],
  threads: [
    { id: 41, root_id: 31, text: "湖底的問句", quote: "湖底", at: now, session: "s-a", stale: false, ended: false },
    { id: 42, root_id: 31, text: "山是否多餘", quote: "山", at: now, session: "s-a", stale: true, ended: false },
    { id: 43, root_id: 32, text: "海豚那句", quote: "海豚", at: now, session: "s-b", stale: false, ended: true },
  ],
  ...over,
});

let memories: MockInstance<typeof api.memories>;
let works: MockInstance<typeof api.memoryWorks>;
let remember: MockInstance<typeof api.remember>;
let setEnded: MockInstance<typeof api.setThreadEnded>;

const mount = () => render(<MemoryRouter initialEntries={["/settings"]}><MemoryPage /></MemoryRouter>);
const header = async (name: string) => within(await screen.findByRole("group", { name })).getAllByRole("button")[0];
const names = () => [...document.querySelectorAll(".dash-mg-group")].map(g => g.getAttribute("aria-label"));
const open = async (name: string) => { fireEvent.click(await header(name)); return screen.getByRole("group", { name }); };

beforeEach(() => {
  localStorage.clear();
  setLang("zh-Hant");
  memories = vi.spyOn(api, "memories").mockResolvedValue(list(
    mem({ id: 1, scope: "work", slug: "d1", title: "海", text: "括號是牠沒說的" }),
    mem({ id: 2, scope: "work", slug: "d1", title: "海", text: "想留白" }),
  ));
  works = vi.spyOn(api, "memoryWorks").mockResolvedValue([sea(), { slug: "d2", title: "山", digests: [], threads: [] }]);
  remember = vi.spyOn(api, "remember").mockResolvedValue(mem({ id: 9 }));
  setEnded = vi.spyOn(api, "setThreadEnded").mockResolvedValue(undefined);
  vi.spyOn(api, "candidates").mockResolvedValue([]);
  vi.spyOn(api, "priorEnabled").mockResolvedValue(true);
  vi.spyOn(api, "suggestEnabled").mockResolvedValue(true);
});
afterEach(() => vi.restoreAllMocks());

describe("MemoryGroups", () => {
  it("groups start collapsed with counts", async () => {
    mount();
    const h = await header("海");
    expect(h.getAttribute("aria-expanded")).toBe("false");
    expect(within(h).getByLabelText("記憶 2")).toBeTruthy();
    expect(within(h).getByLabelText("待續話題 1")).toBeTruthy();
    expect(within(h).getByLabelText("對話摘要 3")).toBeTruthy();
    expect(screen.queryByText("括號是牠沒說的")).toBeNull();
    expect(names()).toEqual(["關於我", "海"]);
    const rest = screen.getByRole("button", { name: "另有 1 篇無記錄" });
    expect(rest.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(rest);
    const quiet = await header("山");
    expect(within(quiet).queryByLabelText(/記憶 |待續話題 |對話摘要 /)).toBeNull();
    expect(names()).toEqual(["關於我", "海", "山"]);
  });

  it("stale thread has no end button", async () => {
    mount();
    const g = await open("海");
    const li = within(g).getByText("山是否多餘").closest("li") as HTMLElement;
    expect(within(li).getByText("原文已修改")).toBeTruthy();
    expect(within(li).queryByRole("button", { name: "標為已結束" })).toBeNull();
    const ended = within(g).getByText("海豚那句").closest("li") as HTMLElement;
    expect(within(ended).getByRole("button", { name: "取消已結束" }).textContent).toBe("✓");
  });

  it("end thread reloads works only and keeps group open", async () => {
    mount();
    const g = await open("海");
    const [m0, w0] = [memories.mock.calls.length, works.mock.calls.length];
    works.mockResolvedValue([sea({ threads: sea().threads.map(x => (x.id === 41 ? { ...x, ended: true } : x)) })]);
    fireEvent.click(within(g).getByRole("button", { name: "標為已結束" }));
    await waitFor(() => expect(setEnded).toHaveBeenCalledWith(41, true));
    await waitFor(() => expect(works.mock.calls.length).toBe(w0 + 1));
    expect(memories.mock.calls.length).toBe(m0);
    const again = await screen.findByRole("group", { name: "海" });
    expect(within(again).getAllByRole("button", { name: "取消已結束" })).toHaveLength(2);
  });

  it("thread links back to its chat", async () => {
    mount();
    const g = await open("海");
    const li = within(g).getByText("湖底的問句").closest("li") as HTMLElement;
    expect(within(li).getByRole("link", { name: "前往原對話" }).getAttribute("href")).toBe("/w/d1?s=s-a");
  });

  it("digest history revert", async () => {
    const versions = vi.spyOn(api, "digestVersions").mockResolvedValue([
      { id: 34, text: "聊了結尾的嘻。", edited: true, created_at: 2, current: true },
      { id: 31, text: "舊的摘要", edited: false, created_at: 1, current: false },
    ]);
    const rev = vi.spyOn(api, "revertDigest").mockResolvedValue({ id: 35 });
    mount();
    const g = await open("海");
    const hist = within(g).getAllByRole("button", { name: "歷史版本" });
    expect(hist).toHaveLength(1);
    fireEvent.click(hist[0]);
    await waitFor(() => expect(versions).toHaveBeenCalledWith(31));
    fireEvent.click(await within(g).findByRole("button", { name: "還原" }));
    await waitFor(() => expect(rev).toHaveBeenCalledWith(31));
  });

  it("digest edit saves a new version", async () => {
    const ed = vi.spyOn(api, "editDigest").mockResolvedValue({ id: 36 });
    mount();
    const g = await open("海");
    const li = within(g).getByText("海豚那段。").closest("li") as HTMLElement;
    fireEvent.click(within(li).getByRole("button", { name: "編輯" }));
    fireEvent.change(within(li).getByRole("textbox"), { target: { value: "改過的摘要" } });
    fireEvent.click(within(li).getByRole("button", { name: "儲存" }));
    await waitFor(() => expect(ed).toHaveBeenCalledWith(32, "改過的摘要"));
  });

  it("manual add uses group scope", async () => {
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "另有 1 篇無記錄" }));
    const g = await open("山");
    fireEvent.click(within(g).getByRole("button", { name: "手動新增" }));
    fireEvent.change(within(g).getByRole("textbox", { name: "新增記憶" }), { target: { value: "關於山" } });
    fireEvent.click(within(g).getByRole("button", { name: "新增" }));
    await waitFor(() => expect(remember).toHaveBeenCalledWith({ scope: "work", slug: "d2", text: "關於山" }));
    const me = screen.getByRole("group", { name: "關於我" });
    fireEvent.change(within(me).getByRole("textbox", { name: "新增記憶" }), { target: { value: "我" } });
    fireEvent.click(within(me).getByRole("button", { name: "新增" }));
    await waitFor(() => expect(remember).toHaveBeenCalledWith({ scope: "author", text: "我" }));
  });

  it("archived work memories still shown", async () => {
    memories.mockResolvedValue(list(mem({ id: 5, scope: "work", slug: "old", title: "舊作", text: "封存作品的記憶" })));
    mount();
    const g = await open("舊作");
    expect(within(g).getByText("封存作品的記憶")).toBeTruthy();
    expect(within(g).queryByRole("button", { name: "手動新增" })).toBeNull();
    expect(names()[names().length - 1]).toBe("舊作");
  });
});

describe("MemoryGroups layout", () => {
  it("about me is always open with no toggle and shows its usage", async () => {
    memories.mockResolvedValue(list(mem({ id: 1, text: "我的事" })));
    mount();
    const me = await screen.findByRole("group", { name: "關於我" });
    expect(within(me).getByText("我的事")).toBeTruthy();
    expect(within(me).queryByRole("button", { expanded: false })).toBeNull();
    expect(within(me).getByText("3/800")).toBeTruthy();
  });

  it("empty about me opens the add box and writes no hint", async () => {
    memories.mockResolvedValue(list());
    mount();
    const me = await screen.findByRole("group", { name: "關於我" });
    expect(within(me).getByRole("textbox", { name: "新增記憶" })).toBeTruthy();
    expect(within(me).queryByRole("button", { name: "手動新增" })).toBeNull();
  });

  it("open groups are remembered across mounts", async () => {
    const r = mount();
    await open("海");
    r.unmount();
    mount();
    expect((await header("海")).getAttribute("aria-expanded")).toBe("true");
  });

  it("long titles keep the full name as a tooltip", async () => {
    mount();
    const g = await screen.findByRole("group", { name: "海" });
    expect(g.querySelector(".dash-mg-name")?.getAttribute("title")).toBe("海");
  });

  it("quote differing from text shows as a citation, the link is an icon", async () => {
    memories.mockResolvedValue(list(mem({ id: 1, text: "結尾要空", quote: "我想最後那條繩子是空的", session: "s1", seq: 0 })));
    mount();
    const me = await screen.findByRole("group", { name: "關於我" });
    const li = within(me).getByText("結尾要空").closest("li") as HTMLElement;
    expect(li.querySelector("blockquote")?.textContent).toBe("我想最後那條繩子是空的");
    expect(within(li).getByRole("link", { name: "出自對話" }).getAttribute("href")).toBe("/c/s1");
  });

  it("saved candidate: going to it opens the group and marks the new row", async () => {
    vi.spyOn(api, "candidates").mockResolvedValue([{ id: 7, text: "新的一條", quote: "新的一條", scope: "work", session: "s1", seq: 0, slug: "d1", title: "海", at: now }]);
    vi.spyOn(api, "saveCandidate").mockResolvedValue(mem({ id: 70 }));
    mount();
    const s = await screen.findByRole("region", { name: "待確認" });
    memories.mockResolvedValue(list(mem({ id: 70, scope: "work", slug: "d1", title: "海", text: "新的一條" })));
    fireEvent.click(within(s).getByRole("button", { name: "存入本篇" }));
    fireEvent.click(await screen.findByRole("button", { name: "〈海〉" }));
    expect((await header("海")).getAttribute("aria-expanded")).toBe("true");
    const row = await waitFor(() => {
      const el = document.querySelector('[data-mem="70"]');
      expect(el).not.toBeNull();
      return el as HTMLElement;
    });
    expect(row.hasAttribute("data-new")).toBe(true);
  });
});

describe("MemoryGroups review fixes", () => {
  it("works not loaded yet: work memories are not shown as archived", async () => {
    let finish!: (w: WorkOverview[]) => void;
    works.mockImplementation(() => new Promise(r => { finish = r; }));
    mount();
    await waitFor(() => expect(memories).toHaveBeenCalled());
    await new Promise(r => setTimeout(r, 0));
    expect(document.querySelector(".dash-mg-arch")).toBeNull();
    finish([sea()]);
    expect(await screen.findByRole("group", { name: "海" })).toBeTruthy();
    expect(document.querySelector(".dash-mg-arch")).toBeNull();
  });

  it("works failing to load shows the reason", async () => {
    const { DashError } = await import("../src/dash/api");
    works.mockRejectedValue(new DashError(0, "den-down"));
    mount();
    expect((await screen.findByRole("alert")).textContent).toContain("den");
  });

  it("stale digest edit reloads works so the next save uses the new id", async () => {
    const { DashError } = await import("../src/dash/api");
    vi.spyOn(api, "editDigest").mockRejectedValue(new DashError(409, "stale-digest"));
    mount();
    const g = await open("海");
    const w0 = works.mock.calls.length;
    const li = within(g).getByText("海豚那段。").closest("li") as HTMLElement;
    fireEvent.click(within(li).getByRole("button", { name: "編輯" }));
    fireEvent.change(within(li).getByRole("textbox"), { target: { value: "改" } });
    fireEvent.click(within(li).getByRole("button", { name: "儲存" }));
    await waitFor(() => expect(works.mock.calls.length).toBe(w0 + 1));
  });

  it("digest summary expands from the keyboard", async () => {
    mount();
    const g = await open("海");
    const sum = within(g).getByRole("button", { name: "初讀。" });
    expect(sum.getAttribute("aria-expanded")).toBe("false");
    fireEvent.keyDown(sum, { key: "Enter" });
    expect(sum.getAttribute("aria-expanded")).toBe("true");
  });
});

describe("MemoryPending layout", () => {
  it("section and dot do not share a class", async () => {
    vi.spyOn(api, "candidates").mockResolvedValue([{ id: 1, text: "甲", quote: "甲", scope: "author", session: "s", seq: 0, slug: null, title: null, at: now }]);
    mount();
    const s = await screen.findByRole("region", { name: "待確認" });
    expect(s.classList.contains("dash-pend")).toBe(false);
  });
});
