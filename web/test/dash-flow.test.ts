import { describe, it, expect, beforeEach } from "vitest";
import { createElement } from "react";
import { render, act } from "@testing-library/react";
import { loadPaperFlow, setPaperFlow, usePaperFlow, PAPER_FLOW_KEY } from "../src/dash/paperFlow";

describe("排法 store", () => {
  beforeEach(() => { localStorage.clear(); act(() => setPaperFlow(loadPaperFlow())); });

  it("沒存 → 直排;存 h → 橫排;不認得 → 直排", () => {
    expect(loadPaperFlow()).toBe("v");
    localStorage.setItem(PAPER_FLOW_KEY, "h");
    expect(loadPaperFlow()).toBe("h");
    localStorage.setItem(PAPER_FLOW_KEY, "x");
    expect(loadPaperFlow()).toBe("v");
  });

  it("setPaperFlow 寫 localStorage,兩個訂閱者都跟著變", () => {
    const Show = ({ id }: { id: string }) => createElement("output", { "data-testid": id }, usePaperFlow());
    const { getByTestId } = render(createElement("div", null, createElement(Show, { id: "a" }), createElement(Show, { id: "b" })));
    expect(getByTestId("a").textContent).toBe("v");
    act(() => setPaperFlow("h"));
    expect(localStorage.getItem(PAPER_FLOW_KEY)).toBe("h");
    expect(getByTestId("a").textContent).toBe("h");
    expect(getByTestId("b").textContent).toBe("h");
  });
});
