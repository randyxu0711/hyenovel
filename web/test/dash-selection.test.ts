import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSelectionQuote } from "../src/dash/useSelectionQuote";

function select(node: Node, text: string) {
  const range = document.createRange();
  range.selectNodeContents(node);
  const sel = document.getSelection()!;
  sel.removeAllRanges();
  sel.addRange(range);
  expect(sel.toString()).toBe(text);
  document.dispatchEvent(new Event("selectionchange"));
}

function setup() {
  const inside = document.createElement("p");
  const outside = document.createElement("p");
  const box = document.createElement("div");
  box.append(inside);
  document.body.append(box, outside);
  return { inside, outside, box };
}

describe("useSelectionQuote", () => {
  it("container 內的選取算", () => {
    const { inside, box } = setup();
    inside.textContent = "海很深";
    const { result } = renderHook(() => useSelectionQuote({ current: box }));
    act(() => select(inside.firstChild!, "海很深"));
    expect(result.current).toMatchObject({ quote: "海很深", tooLong: false });
  });
  it("selectionchange 在 container 外不算", () => {
    const { outside, box } = setup();
    outside.textContent = "外面的字";
    const { result } = renderHook(() => useSelectionQuote({ current: box }));
    act(() => select(outside.firstChild!, "外面的字"));
    expect(result.current.quote).toBeNull();
  });
  it("超過 400 字 tooLong;clear 清掉", () => {
    const { inside, box } = setup();
    inside.textContent = "字".repeat(401);
    const { result } = renderHook(() => useSelectionQuote({ current: box }));
    act(() => select(inside.firstChild!, "字".repeat(401)));
    expect(result.current.tooLong).toBe(true);
    act(() => result.current.clear());
    expect(result.current.quote).toBeNull();
  });
  it("剛好 400 字不算太長", () => {
    const { inside, box } = setup();
    inside.textContent = "字".repeat(400);
    const { result } = renderHook(() => useSelectionQuote({ current: box }));
    act(() => select(inside.firstChild!, "字".repeat(400)));
    expect(result.current.tooLong).toBe(false);
  });
  it("字數以 code point 算(跟 den 同):400 個 𠀋 不算太長", () => {
    const { inside, box } = setup();
    inside.textContent = "𠀋".repeat(400);
    const { result } = renderHook(() => useSelectionQuote({ current: box }));
    act(() => select(inside.firstChild!, "𠀋".repeat(400)));
    expect(result.current.tooLong).toBe(false);
  });
});
