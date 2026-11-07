import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useEffect } from "react";
import { LinksProvider, useLinks } from "../src/dash/links";
import Iq from "../src/dash/Iq";

const span = { quote: "海很深", start: 3, end: 6 };

function Spy({ fn }: { fn: (s: unknown) => void }) {
  const { registerPaper } = useLinks();
  useEffect(() => registerPaper(fn), [registerPaper, fn]);
  return null;
}

const mount = (s: typeof span | { quote: string; start: null; end: null }, fn = vi.fn()) => {
  render(<LinksProvider><Spy fn={fn} /><Iq span={s as never} version={1} /></LinksProvider>);
  return fn;
};

describe("Iq", () => {
  it("是行內元素(可跨行斷),不是 button", () => {
    mount(span);
    expect(screen.getByRole("button", { name: "「海很深」" }).tagName).toBe("SPAN");
  });

  it("Enter 和空白鍵跟點擊一樣跳到稿", () => {
    const fn = mount(span);
    const el = screen.getByRole("button", { name: "「海很深」" });
    fireEvent.keyDown(el, { key: "Enter" });
    fireEvent.keyDown(el, { key: " " });
    fireEvent.click(el);
    expect(fn).toHaveBeenCalledTimes(3);
  });

  it("這版對不到的引文不跳", () => {
    const fn = mount({ quote: "海很深", start: null, end: null });
    fireEvent.click(screen.getByRole("button", { name: "「海很深」" }));
    expect(fn).not.toHaveBeenCalled();
  });
});
