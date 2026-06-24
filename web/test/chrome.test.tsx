import { describe, it, expect, vi } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import Chrome from "../src/journey/Chrome";

describe("Chrome", () => {
  it("overview 不顯示麵包屑/退", () => {
    const { container } = render(<Chrome stage="overview" onBack={vi.fn()} />);
    expect(container.querySelector(".crumb")).toBeNull();
    expect(container.querySelector(".chrome-back")).toBeNull();
  });
  it("single 顯示麵包屑含標題,退鈕呼叫 onBack", () => {
    const onBack = vi.fn();
    const { container, getByText } = render(<Chrome stage="single" title="長夜" onBack={onBack} />);
    expect(getByText(/長夜/)).toBeTruthy();
    fireEvent.click(container.querySelector(".chrome-back")!);
    expect(onBack).toHaveBeenCalled();
  });
});
