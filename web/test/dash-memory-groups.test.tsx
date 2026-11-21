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
    const g = await open("山");
    fireEvent.click(within(g).getByRole("button", { name: "手動新增" }));
    fireEvent.change(within(g).getByRole("textbox", { name: "新增記憶" }), { target: { value: "關於山" } });
    fireEvent.click(within(g).getByRole("button", { name: "新增" }));
    await waitFor(() => expect(remember).toHaveBeenCalledWith({ scope: "work", slug: "d2", text: "關於山" }));
    const me = await open("關於我");
    fireEvent.click(within(me).getByRole("button", { name: "手動新增" }));
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
