import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ToneLab from "../src/lab/ToneLab";

// /lab/tone 是字階驗收樣張(spec §4:視覺的閘門是使用者的眼睛)。
// 這裡只守「八階都真的擺出來了」——好不好看不是測試的事。

let ctx: { clearRect: ReturnType<typeof vi.fn>; beginPath: ReturnType<typeof vi.fn>; arc: ReturnType<typeof vi.fn>; fill: ReturnType<typeof vi.fn> };

beforeEach(() => {
  // jsdom 沒有 2d context;給個樁避免 throw(Dust 內用)
  ctx = { clearRect: vi.fn(), beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn() };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(ctx as unknown as CanvasRenderingContext2D);
});

describe("/lab/tone", () => {
  it("八個字階 token 各有一列樣張(舊/新並排)", () => {
    render(<MemoryRouter><ToneLab /></MemoryRouter>);
    for (const tok of ["--t-micro", "--t-caption", "--t-body", "--t-lead",
                       "--t-title", "--t-display", "--t-hero", "--t-total"])
      expect(screen.getByText(new RegExp(tok))).toBeTruthy();
    expect(screen.getAllByText("海口的暗暝").length).toBeGreaterThanOrEqual(2); // 舊新兩欄都在
  });

  it("大氣樣張:前/後兩片天 + 四開關(冷底/視差塵埃/grain/星暈),預設全開", () => {
    render(<MemoryRouter><ToneLab /></MemoryRouter>);
    expect(document.querySelectorAll(".tone-sky").length).toBe(2);
    for (const name of ["冷底", "視差塵埃", "grain", "星暈"]) {
      const cb = screen.getByLabelText(name) as HTMLInputElement;
      expect(cb.checked).toBe(true);
    }
  });
});
