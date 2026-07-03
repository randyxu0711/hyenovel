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
});
