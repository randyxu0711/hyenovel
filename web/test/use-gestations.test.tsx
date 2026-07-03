import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";

const running = vi.fn();
const stream = vi.fn();
const cancel = vi.fn();
vi.mock("../src/data/client", () => ({
  getRunningCritiques: () => running(),
  streamCritique: (slug: string, title: string) => stream(slug, title),
  cancelCritique: (slug: string) => cancel(slug),
}));
import { useGestations } from "../src/journey/useGestations";

async function* gen(evs: unknown[]) { for (const e of evs) yield e; }

beforeEach(() => { running.mockReset(); stream.mockReset(); cancel.mockReset(); });

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
});
