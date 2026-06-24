import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import IntentionChain from "../src/viz/IntentionChain";
import viz from "./fixtures/viz.json";
import type { VizData } from "../src/types";

describe("IntentionChain interaction", () => {
  it("點節點呼叫 onPick(id) 且不冒泡成 onPick(null)", () => {
    const onPick = vi.fn();
    const v = viz as unknown as VizData;
    const { container } = render(<IntentionChain viz={v} selected={null} onPick={onPick} />);
    const node = container.querySelector("g.cnode") as SVGGElement;
    fireEvent.click(node);
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick).not.toHaveBeenCalledWith(null);
  });
});
