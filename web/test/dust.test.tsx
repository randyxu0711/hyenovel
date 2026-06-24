import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import Dust from "../src/journey/Dust";

beforeEach(() => {
  // jsdom 沒有 2d context;給個樁避免 throw
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    clearRect: vi.fn(), beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(),
  } as unknown as CanvasRenderingContext2D);
});

describe("Dust", () => {
  it("render 一個 canvas.dust", () => {
    const { container } = render(<Dust />);
    expect(container.querySelector("canvas.dust")).toBeTruthy();
  });
});
