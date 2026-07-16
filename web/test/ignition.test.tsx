import { describe, it, expect, vi, afterEach } from "vitest";
import { render, act } from "@testing-library/react";
import Ignition, { IGNITION_MS } from "../src/journey/Ignition";

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("Ignition", () => {
  it("播完動畫後才呼叫一次 onDone", () => {
    vi.useFakeTimers();
    const onDone = vi.fn();
    render(<Ignition onDone={onDone} />);
    expect(onDone).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(IGNITION_MS + 20); });
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("reduced-motion 時立即 onDone、不播風化 SVG", () => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true }));
    const onDone = vi.fn();
    const { container } = render(<Ignition onDone={onDone} />);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(container.querySelector(".ign-weather")).toBeNull();
  });
});
