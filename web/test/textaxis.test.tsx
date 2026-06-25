import { describe, it, expect, vi } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import TextAxis from "../src/viz/TextAxis";
import viz from "./fixtures/viz.json";
import type { VizData } from "../src/types";

describe("TextAxis", () => {
  it("每個 beat 點畫一條肋線", () => {
    const v = viz as unknown as VizData;
    const beatCount = v.nodes.filter(n => n.type === "beat").length;
    const { container } = render(<TextAxis viz={v} onPick={vi.fn()} />);
    expect(container.querySelectorAll("line.rib").length).toBe(beatCount);
  });

  it("每個 mark 標籤常駐顯示(泳道:不必 hover 就能掃讀)", () => {
    const v = viz as unknown as VizData;
    const mark = v.nodes.find(n => (n.type === "technique" || n.type === "effect") && n.evidence.some(e => e.pos != null))!;
    const { container } = render(<TextAxis viz={v} onPick={vi.fn()} />);
    expect(container.querySelector(`text[data-label="${mark.id}"]`)).toBeTruthy();
  });

  it("點 mark 觸發 onPick(id)", () => {
    const v = viz as unknown as VizData;
    const mark = v.nodes.find(n => (n.type === "technique" || n.type === "effect") && n.evidence.some(e => e.pos != null))!;
    const onPick = vi.fn();
    const { container } = render(<TextAxis viz={v} onPick={onPick} />);
    fireEvent.click(container.querySelector(`g.cnode[data-id="${mark.id}"]`)!);
    expect(onPick).toHaveBeenCalledWith(mark.id);
  });
});
