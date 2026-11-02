import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { useShelf, SHELF_KEY } from "../src/dash/useShelf";
import { clampSide } from "../src/dash/Dash";

const W0 = window.innerWidth;
const setWidth = (w: number) => { Object.defineProperty(window, "innerWidth", { configurable: true, value: w }); };
beforeEach(() => localStorage.clear());
afterEach(() => setWidth(W0));

function Probe() {
  const { mode, toggle } = useShelf();
  return <button onClick={toggle}>{mode}</button>;
}

describe("useShelf", () => {
  it("沒存過:寬 1280 → open;1279 → rail", () => {
    setWidth(1280);
    const a = render(<Probe />);
    expect(screen.getByRole("button").textContent).toBe("open");
    a.unmount();
    setWidth(1279);
    render(<Probe />);
    expect(screen.getByRole("button").textContent).toBe("rail");
  });
  it("存過的優先;壞值當沒存過", () => {
    setWidth(1600);
    localStorage.setItem(SHELF_KEY, "rail");
    const a = render(<Probe />);
    expect(screen.getByRole("button").textContent).toBe("rail");
    a.unmount();
    localStorage.setItem(SHELF_KEY, "wide");
    render(<Probe />);
    expect(screen.getByRole("button").textContent).toBe("open");
  });
  it("toggle 寫回 localStorage", () => {
    setWidth(1600);
    render(<Probe />);
    act(() => fireEvent.click(screen.getByRole("button")));
    expect(screen.getByRole("button").textContent).toBe("rail");
    expect(localStorage.getItem(SHELF_KEY)).toBe("rail");
  });
});

describe("clampSide", () => {
  it("右欄最寬 = 視窗 − 書架實際寬 − 分隔線 − 稿最少 380;最窄 380", () => {
    setWidth(1600);
    expect(clampSide(9999, 244)).toBe(1600 - 244 - 9 - 380);
    expect(clampSide(9999, 56)).toBe(1600 - 56 - 9 - 380);
    expect(clampSide(10, 244)).toBe(380);
  });
});
