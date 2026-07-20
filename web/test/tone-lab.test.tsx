import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ToneLab from "../src/lab/ToneLab";

// /lab/tone 是字階驗收樣張(spec §4:視覺的閘門是使用者的眼睛)。
// 這裡只守「八階都真的擺出來了」——好不好看不是測試的事。
describe("/lab/tone", () => {
  it("八個字階 token 各有一列樣張(舊/新並排)", () => {
    render(<MemoryRouter><ToneLab /></MemoryRouter>);
    for (const tok of ["--t-micro", "--t-caption", "--t-body", "--t-lead",
                       "--t-title", "--t-display", "--t-hero", "--t-total"])
      expect(screen.getByText(new RegExp(tok))).toBeTruthy();
    expect(screen.getAllByText("海口的暗暝").length).toBeGreaterThanOrEqual(2); // 舊新兩欄都在
  });
});
