import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, render } from "@testing-library/react";
import Dust from "../src/journey/Dust";

let ctx: { clearRect: ReturnType<typeof vi.fn>; beginPath: ReturnType<typeof vi.fn>; arc: ReturnType<typeof vi.fn>; fill: ReturnType<typeof vi.fn> };

beforeEach(() => {
  // jsdom 沒有 2d context;給個樁避免 throw
  ctx = { clearRect: vi.fn(), beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn() };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(ctx as unknown as CanvasRenderingContext2D);
});

describe("Dust", () => {
  it("render 一個 canvas.dust", () => {
    const { container } = render(<Dust />);
    expect(container.querySelector("canvas.dust")).toBeTruthy();
  });

  it("減動模式下 resize 清空畫布後仍會重畫(不留空白)", () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({ matches: true } as MediaQueryList);
    render(<Dust cam={{ x: -100, y: 0 }} />);
    expect(ctx.fill).toHaveBeenCalled();   // mount:靜態幀已畫
    ctx.fill.mockClear();
    act(() => { window.dispatchEvent(new Event("resize")); });
    // resize 會先 init() 清空畫布點陣,若沒人重畫就會停在空白 —— 這裡斷言確實重畫了
    expect(ctx.fill).toHaveBeenCalled();
  });
});
