import { describe, it, expect, vi } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import DropSheet from "../src/dash/DropSheet";

const files = (f: File[] = [new File(["x"], "海.md")]) => ({ dataTransfer: { types: ["Files"], files: f } });
const text = { dataTransfer: { types: ["text/plain"], files: [] } };
const sheet = (c: HTMLElement) => c.querySelector(".drop-sheet");

describe("DropSheet(整個畫面收檔)", () => {
  it("拖檔案進來 → 蓋層出現,寫下一版號", () => {
    const { container } = render(<DropSheet next={3} onFile={vi.fn()} />);
    expect(sheet(container)).toBeNull();
    fireEvent.dragEnter(window, files());
    expect(sheet(container)!.textContent).toContain("v3");
  });
  it("拖的是文字 → 不出現", () => {
    const { container } = render(<DropSheet next={3} onFile={vi.fn()} />);
    fireEvent.dragEnter(window, text);
    expect(sheet(container)).toBeNull();
  });
  it("進子元素再出來不閃:enter×2、leave×1 仍在;再 leave → 消失", () => {
    const { container } = render(<DropSheet next={3} onFile={vi.fn()} />);
    fireEvent.dragEnter(window, files());
    fireEvent.dragEnter(window, files());
    fireEvent.dragLeave(window, files());
    expect(sheet(container)).not.toBeNull();
    fireEvent.dragLeave(window, files());
    expect(sheet(container)).toBeNull();
  });
  it("放開 → onFile 收到第一個檔、蓋層收掉", () => {
    const onFile = vi.fn();
    const f = new File(["x"], "海.md");
    const { container } = render(<DropSheet next={3} onFile={onFile} />);
    fireEvent.dragEnter(window, files([f]));
    fireEvent.drop(window, files([f]));
    expect(onFile).toHaveBeenCalledWith(f);
    expect(sheet(container)).toBeNull();
  });
  it("文字放開 → 不交檔", () => {
    const onFile = vi.fn();
    render(<DropSheet next={3} onFile={onFile} />);
    fireEvent.drop(window, text);
    expect(onFile).not.toHaveBeenCalled();
  });
});
