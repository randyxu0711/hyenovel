import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { api, DashError } from "../src/dash/api";
import { useSubmitDraft } from "../src/dash/useSubmitDraft";

afterEach(() => vi.restoreAllMocks());

function mount(est: object | null = null) {
  vi.spyOn(api, "estimate").mockResolvedValue(est as never);
  return renderHook(() => useSubmitDraft());
}
const sub = (o: object = {}) => vi.spyOn(api, "submit").mockResolvedValue({ slug: "d3", title: "t", version: 1, new_version: true, reused: false, ...o });

describe("useSubmitDraft", () => {
  it("一開始沒有稿;貼上後有字數與預估(null 預估 = 第一次分析)", async () => {
    const { result } = mount(null);
    expect(result.current.draft).toBeNull();
    act(() => result.current.fromText("一段稿子"));
    expect(result.current.draft?.chars).toBe(4);
    await waitFor(() => expect(result.current.draft?.estimate).toEqual({ v: null }));
  });
  it("有預估時帶回預估值", async () => {
    const { result } = mount({ seconds: 300, output_tokens: 1, basis: 2 });
    act(() => result.current.fromText("一段稿子"));
    await waitFor(() => expect(result.current.draft?.estimate?.v?.seconds).toBe(300));
  });
  it("選檔走 extract,標題取檔名;確認後以該標題交稿並開 job", async () => {
    const { result } = mount();
    vi.spyOn(api, "extract").mockResolvedValue({ filename: "海.md", text: "檔案內容", chars: 4 });
    const s = sub();
    const start = vi.spyOn(api, "startJob").mockResolvedValue({ job_id: 7 });
    await act(() => result.current.fromFile(new File(["x"], "海.md")));
    expect(result.current.draft?.text).toBe("檔案內容");
    let r: unknown;
    await act(async () => { r = await result.current.confirm(); });
    expect(s).toHaveBeenCalledWith("檔案內容", "海");
    expect(start).toHaveBeenCalledWith("d3");
    expect(r).toMatchObject({ slug: "d3", reused: false });
    expect(result.current.draft).toBeNull();
  });
  it("reused 但還沒分析(none/stopped/notes-stopped):補開 job", async () => {
    const { result } = mount();
    sub({ slug: "d1", reused: true, new_version: false });
    vi.spyOn(api, "work").mockResolvedValue({ slug: "d1", title: "t", version: 1, text: "", state: "none", job_id: null, notes_ready: false, versions: [1] });
    const start = vi.spyOn(api, "startJob").mockResolvedValue({ job_id: 3 });
    act(() => result.current.fromText("稿"));
    let r: any;
    await act(async () => { r = await result.current.confirm(); });
    expect(start).toHaveBeenCalledWith("d1");
    expect(r.reused).toBe(true);
  });
  it("reused 且已分析完:不呼叫 startJob", async () => {
    const { result } = mount();
    sub({ slug: "d1", reused: true, new_version: false });
    vi.spyOn(api, "work").mockResolvedValue({ slug: "d1", title: "t", version: 1, text: "", state: "ready", job_id: null, notes_ready: true, versions: [1] });
    const start = vi.spyOn(api, "startJob");
    act(() => result.current.fromText("稿"));
    await act(async () => { await result.current.confirm(); });
    expect(start).not.toHaveBeenCalled();
  });
  it("失敗:error 帶 den 的代碼、稿還在、回 null,可再試", async () => {
    const { result } = mount();
    vi.spyOn(api, "submit").mockRejectedValue(new DashError(422, "story-too-long"));
    act(() => result.current.fromText("稿"));
    let r: unknown = 1;
    await act(async () => { r = await result.current.confirm(); });
    expect(r).toBeNull();
    expect(result.current.error).toBe("story-too-long");
    expect(result.current.draft?.text).toBe("稿");
    expect(result.current.busy).toBe(false);
  });
  it("extract 失敗:error,沒有稿", async () => {
    const { result } = mount();
    vi.spyOn(api, "extract").mockRejectedValue(new DashError(422, "extract-failed"));
    await act(() => result.current.fromFile(new File(["x"], "a.md")));
    expect(result.current.error).toBe("extract-failed");
    expect(result.current.draft).toBeNull();
  });
  it("cancel 丟掉稿與錯誤", () => {
    const { result } = mount();
    act(() => result.current.fromText("稿"));
    act(() => result.current.cancel());
    expect(result.current.draft).toBeNull();
  });
  it("沒有稿時 confirm 什麼都不做", async () => {
    const { result } = mount();
    const s = sub();
    let r: unknown = 1;
    await act(async () => { r = await result.current.confirm(); });
    expect(r).toBeNull();
    expect(s).not.toHaveBeenCalled();
  });
});
