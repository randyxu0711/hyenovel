import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";

const running = vi.fn();
const stream = vi.fn();
const cancel = vi.fn();
const idx = vi.fn();
const reanalyzeStream = vi.fn();
vi.mock("../src/data/client", () => ({
  getRunningCritiques: () => running(),
  streamCritique: (slug: string, title: string) => stream(slug, title),
  cancelCritique: (slug: string) => cancel(slug),
  getIndex: () => idx(),
  reanalyzeCritique: (slug: string, title: string) => reanalyzeStream(slug, title),
}));
import { useGestations } from "../src/journey/useGestations";

async function* gen(evs: unknown[]) { for (const e of evs) yield e; }

beforeEach(() => {
  running.mockReset(); stream.mockReset(); cancel.mockReset(); localStorage.clear();
  // 預設空 index:大多數測試不關心「初載併入 resumable 故事」這條路徑,只有專門測試會覆寫。
  idx.mockReset().mockResolvedValue({ generated: "", count: 0, stories: [] });
  reanalyzeStream.mockReset();
});

describe("useGestations", () => {
  it("載入時把 /running 併入孕育態", async () => {
    running.mockResolvedValue([{ slug: "a", title: "甲", status: "running", step: 2 }]);
    stream.mockReturnValue(gen([]));
    const { result } = renderHook(() => useGestations(() => {}));
    await waitFor(() => expect(result.current.gestations.get("a")?.step).toBe(2));
  });

  it("begin 後 phase 推進 step;done → 呼 onBorn 並移除", async () => {
    running.mockResolvedValue([]);
    const onBorn = vi.fn();
    stream.mockReturnValue(gen([
      { event: "phase", data: { name: "analyst", status: "ok" } },  // → step 2
      { event: "done", data: {} },
    ]));
    const { result } = renderHook(() => useGestations(onBorn));
    act(() => result.current.begin("b", "乙"));
    expect(stream).toHaveBeenCalledWith("b", "乙");
    await waitFor(() => expect(onBorn).toHaveBeenCalledWith("b"));
    expect(result.current.gestations.has("b")).toBe(false);
  });

  it("phase preview ok → vizReady,且不動 step(preview 不是一格)", async () => {
    running.mockResolvedValue([]);
    stream.mockReturnValue(gen([
      { event: "phase", data: { name: "analyst", status: "ok" } },    // → step 2
      { event: "phase", data: { name: "preview", status: "ok" } },    // 早出 viz 落檔
    ]));
    const { result } = renderHook(() => useGestations(() => {}));
    act(() => result.current.begin("p", "預覽"));
    await waitFor(() => expect(result.current.gestations.get("p")?.vizReady).toBe(true));
    expect(result.current.gestations.get("p")?.step, "preview 不該把 step 推掉").toBe(2);
  });

  it("phase preview skip(產失敗)→ 不給 vizReady,續用象徵骨", async () => {
    running.mockResolvedValue([]);
    stream.mockReturnValue(gen([
      { event: "phase", data: { name: "analyst", status: "ok" } },
      { event: "phase", data: { name: "preview", status: "skip" } },
    ]));
    const { result } = renderHook(() => useGestations(() => {}));
    act(() => result.current.begin("q", "跳過"));
    await waitFor(() => expect(result.current.gestations.get("q")?.step).toBe(2));
    expect(result.current.gestations.get("q")?.vizReady).toBeFalsy();
  });

  it("cancel 呼叫後端並移除", async () => {
    running.mockResolvedValue([]);
    cancel.mockResolvedValue(true);
    stream.mockReturnValue(gen([{ event: "phase", data: { name: "analyst", status: "start" } }]));
    const { result } = renderHook(() => useGestations(() => {}));
    act(() => result.current.begin("c", "丙"));
    await waitFor(() => expect(result.current.gestations.has("c")).toBe(true));
    act(() => result.current.cancel("c"));
    expect(cancel).toHaveBeenCalledWith("c");
    await waitFor(() => expect(result.current.gestations.has("c")).toBe(false));
  });

  it("cancel 後立刻重 begin 同篇:重新訂閱,舊串流的 error 不誤刪新胎", async () => {
    running.mockResolvedValue([]);
    cancel.mockResolvedValue(true);
    let releaseErr1: () => void = () => {};
    const s1 = (async function* () {
      yield { event: "phase", data: { name: "analyst", status: "start" } };   // 先讓它 alive(step1)
      await new Promise<void>(r => { releaseErr1 = r; });                       // 掛住,等測試放行
      yield { event: "error", data: { where: "cancel", message: "已取消" } };  // 舊串流的取消 error
    })();
    const s2 = gen([{ event: "phase", data: { name: "analyst", status: "ok" } }]); // 新胎推到 step2
    stream.mockReturnValueOnce(s1).mockReturnValueOnce(s2);

    const { result } = renderHook(() => useGestations(() => {}));
    act(() => result.current.begin("d", "丁"));
    await waitFor(() => expect(result.current.gestations.get("d")?.step).toBe(1));
    act(() => result.current.cancel("d"));       // 作廢第一條訂閱
    act(() => result.current.begin("d", "丁"));   // 立刻重 begin → 應開第二條(不被 dedup 擋)
    await waitFor(() => expect(result.current.gestations.get("d")?.step).toBe(2)); // 第二條推進 = 有重新訂閱
    act(() => { releaseErr1(); });                // 第一條(舊)此時才吐 error
    await new Promise(r => setTimeout(r, 10));
    expect(result.current.gestations.get("d")?.step).toBe(2);   // 舊 error 未誤刪新胎
  });

  it("error 事件(非取消)→ 移除孕育星", async () => {
    running.mockResolvedValue([]);
    stream.mockReturnValue(gen([{ event: "error", data: { where: "run", message: "壞了" } }]));
    const { result } = renderHook(() => useGestations(() => {}));
    act(() => result.current.begin("e", "戊"));
    await waitFor(() => expect(result.current.gestations.has("e")).toBe(false));
  });

  it("error reason=usage-limit(未來 resets_at)→ 設 usageLimitResetAt 供 UI + 持久化;不 drop、改標 paused;dismiss 清提示", async () => {
    running.mockResolvedValue([]);
    const future = Math.floor(Date.now() / 1000) + 3600;
    stream.mockReturnValue(gen([{ event: "error", data: { reason: "usage-limit", resets_at: future } }]));
    const { result } = renderHook(() => useGestations(() => {}));
    expect(result.current.usageLimitResetAt).toBeUndefined();
    act(() => result.current.begin("f", "己"));
    await waitFor(() => expect(result.current.usageLimitResetAt).toBe(future));
    expect(result.current.gestations.get("f")?.status).toBe("paused");   // 不 drop:停在原拍,留給使用者續跑
    expect(result.current.gestations.get("f")?.reason).toBe("usage-limit");
    expect(localStorage.getItem("hy:usageLimit")).toBe(String(future));  // 跨 F5 存下
    act(() => result.current.dismissUsageLimit());                      // 只清全域提示,胚胎狀態不受影響
    expect(result.current.usageLimitResetAt).toBeUndefined();
    expect(localStorage.getItem("hy:usageLimit")).toBeNull();
    expect(result.current.gestations.get("f")?.status).toBe("paused");
  });

  it("已過期的 resets_at → 讀取即清、不顯示(胚胎仍標 paused,不受影響)", async () => {
    running.mockResolvedValue([]);
    const past = Math.floor(Date.now() / 1000) - 10;
    stream.mockReturnValue(gen([{ event: "error", data: { reason: "usage-limit", resets_at: past } }]));
    const { result } = renderHook(() => useGestations(() => {}));
    act(() => result.current.begin("g", "庚"));
    await waitFor(() => expect(result.current.gestations.get("g")?.status).toBe("paused"));
    await waitFor(() => expect(result.current.usageLimitResetAt).toBeUndefined());
    expect(localStorage.getItem("hy:usageLimit")).toBeNull();
  });

  it("error reason ∈ timeout/gate/crash → 不 drop,改標 failed(可續跑/重新分析)", async () => {
    running.mockResolvedValue([]);
    stream.mockReturnValue(gen([{ event: "error", data: { reason: "crash" } }]));
    const { result } = renderHook(() => useGestations(() => {}));
    act(() => result.current.begin("h", "辛"));
    await waitFor(() => expect(result.current.gestations.get("h")?.status).toBe("failed"));
    expect(result.current.gestations.get("h")?.reason).toBe("crash");
  });

  it("初載併入 index 裡 resumable 的故事,標成停住的胎(step 對齊 stage)", async () => {
    running.mockResolvedValue([]);
    idx.mockResolvedValue({
      generated: "", count: 1,
      stories: [{ slug: "i", title: "壬", synopsis: "", nodes: 0, edges: 0, has_feedback: false, has_viz: false,
                  updated: "", status: "paused", stage: "criticizer", resumable: true }],
    });
    const { result } = renderHook(() => useGestations(() => {}));
    await waitFor(() => expect(result.current.gestations.get("i")?.status).toBe("paused"));
    expect(result.current.gestations.get("i")?.step).toBe(2);   // stage=criticizer
  });

  it("index 的 status 是未列舉值(如 cancelled)但 resumable=true → 容忍,標 failed 不炸掉", async () => {
    running.mockResolvedValue([]);
    idx.mockResolvedValue({
      generated: "", count: 1,
      stories: [{ slug: "j", title: "癸", synopsis: "", nodes: 0, edges: 0, has_feedback: false, has_viz: false,
                  updated: "", status: "cancelled", stage: "analyst", resumable: true }],
    });
    const { result } = renderHook(() => useGestations(() => {}));
    await waitFor(() => expect(result.current.gestations.get("j")?.status).toBe("failed"));
  });

  it("index 裡非 resumable 的完整故事 → 不併入孕育態", async () => {
    running.mockResolvedValue([]);
    idx.mockResolvedValue({
      generated: "", count: 1,
      stories: [{ slug: "k", title: "子", synopsis: "", nodes: 1, edges: 1, has_feedback: true, has_viz: true,
                  updated: "", status: "done", stage: "done", resumable: false }],
    });
    const { result } = renderHook(() => useGestations(() => {}));
    await waitFor(() => expect(idx).toHaveBeenCalled());
    expect(result.current.gestations.has("k")).toBe(false);
  });

  it("resume() 重新訂閱(不帶 fresh),step 不倒退", async () => {
    running.mockResolvedValue([]);
    stream.mockReturnValue(gen([]));
    const { result } = renderHook(() => useGestations(() => {}));
    act(() => result.current.resume("m", "丑"));
    expect(stream).toHaveBeenCalledWith("m", "丑");
    await waitFor(() => expect(result.current.gestations.get("m")?.status).toBe("running"));
  });

  it("reanalyze() 呼叫 reanalyzeCritique 並訂閱其串流(一次 POST 觸發+接流)", async () => {
    running.mockResolvedValue([]);
    reanalyzeStream.mockReturnValue(gen([{ event: "phase", data: { name: "analyst", status: "ok" } }]));
    const { result } = renderHook(() => useGestations(() => {}));
    act(() => result.current.reanalyze("n", "寅"));
    expect(reanalyzeStream).toHaveBeenCalledWith("n", "寅");
    await waitFor(() => expect(result.current.gestations.get("n")?.step).toBe(2));
  });

  it("F5:初值讀 localStorage 未過期的 resets_at → 直接顯示(不需重新撞牆)", () => {
    running.mockResolvedValue([]);
    stream.mockReturnValue(gen([]));
    const future = Math.floor(Date.now() / 1000) + 3600;
    localStorage.setItem("hy:usageLimit", String(future));
    const { result } = renderHook(() => useGestations(() => {}));
    expect(result.current.usageLimitResetAt).toBe(future);
  });
});
