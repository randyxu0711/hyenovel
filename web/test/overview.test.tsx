import { describe, it, expect, vi, afterEach } from "vitest";
import { render, act, fireEvent } from "@testing-library/react";
import Overview, { WEATHER_MS } from "../src/journey/Overview";
import Orbits from "../src/journey/Orbits";
import NascentStar from "../src/journey/NascentStar";

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("Overview 點火入口(標題本體風化)", () => {
  it("按 Enter → 標題本體開始飛散,飛淨(WEATHER_MS)後才 onEnter", () => {
    vi.useFakeTimers();
    const onEnter = vi.fn();
    const { container } = render(<Overview onEnter={onEnter} />);
    fireEvent.keyDown(window, { key: "Enter" });
    expect(container.querySelector(".ov-canvas-wrap.igniting")).toBeTruthy();  // 飛散的是原本那個 canvas 標題,非替身
    expect(onEnter).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(WEATHER_MS + 20); });
    expect(onEnter).toHaveBeenCalledTimes(1);
  });

  it("點「進入」也觸發風化", () => {
    vi.useFakeTimers();
    const onEnter = vi.fn();
    const { getByRole } = render(<Overview onEnter={onEnter} />);
    fireEvent.click(getByRole("button", { name: /進入/ }));
    act(() => { vi.advanceTimersByTime(WEATHER_MS + 20); });
    expect(onEnter).toHaveBeenCalledTimes(1);
  });

  it("reduced-motion → 立即 onEnter、不風化", () => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true }));
    const onEnter = vi.fn();
    const { getByRole, container } = render(<Overview onEnter={onEnter} />);
    fireEvent.click(getByRole("button", { name: /進入/ }));
    expect(onEnter).toHaveBeenCalledTimes(1);
    expect(container.querySelector(".ov-canvas-wrap.igniting")).toBeNull();
  });
});

describe("入場綻放用真物體(非替身)", () => {
  it("Orbits bloom → svg 掛 .bloom、各圈帶錯開延遲", () => {
    const { container } = render(<Orbits count={12} bloom />);   // 12 篇 → 至少 2 圈,才驗得到錯開
    expect(container.querySelector("svg.orbits.bloom")).toBeTruthy();
    const ell = container.querySelectorAll("ellipse");
    expect(ell.length).toBeGreaterThanOrEqual(2);
    expect((ell[1] as SVGElement).style.animationDelay).toBe("0.13s");
  });

  it("NascentStar igniting → 真種骨掛 .ignite", () => {
    const { container } = render(<NascentStar onOpen={() => {}} igniting />);
    expect(container.querySelector(".nascent.ignite")).toBeTruthy();
  });
});
