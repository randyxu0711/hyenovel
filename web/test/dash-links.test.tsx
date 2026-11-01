import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import type { ReactNode } from "react";
import { LinksProvider, useLinks } from "../src/dash/links";

const span = { quote: "海", start: 0, end: 1 };
const wrap = ({ children }: { children: ReactNode }) => <LinksProvider>{children}</LinksProvider>;
const mockNarrow = (narrow: boolean) => {
  window.matchMedia = ((q: string) => ({ matches: narrow && q === "(max-width:1100px)", media: q })) as unknown as typeof window.matchMedia;
};

describe("links", () => {
  beforeEach(() => mockNarrow(false));
  afterEach(() => { delete (window as { matchMedia?: unknown }).matchMedia; });

  it("jumpToPaper calls registered fn with span", () => {
    const { result } = renderHook(() => useLinks(), { wrapper: wrap });
    const fn = vi.fn();
    act(() => { result.current.registerPaper(fn); });
    act(() => result.current.jumpToPaper(span));
    expect(fn).toHaveBeenCalledWith(span);
    expect(result.current.pane).toBe("side");
  });

  it("narrow screen switches pane to paper", () => {
    mockNarrow(true);
    const { result } = renderHook(() => useLinks(), { wrapper: wrap });
    act(() => result.current.setPane("side"));
    act(() => result.current.jumpToPaper(span));
    expect(result.current.pane).toBe("paper");
  });

  it("works without matchMedia", () => {
    delete (window as { matchMedia?: unknown }).matchMedia;
    const { result } = renderHook(() => useLinks(), { wrapper: wrap });
    act(() => result.current.jumpToPaper(span));
    expect(result.current.pane).toBe("side");
  });

  it("jumpToTalk false keeps pane; true switches on narrow", () => {
    mockNarrow(true);
    const { result } = renderHook(() => useLinks(), { wrapper: wrap });
    act(() => result.current.setPane("paper"));
    act(() => { result.current.registerTalk(() => false); });
    act(() => result.current.jumpToTalk("x"));
    expect(result.current.pane).toBe("paper");
    act(() => { result.current.registerTalk(() => true); });
    act(() => result.current.jumpToTalk("x"));
    expect(result.current.pane).toBe("side");
  });

  it("unregister stops calls; stale unregister keeps newer", () => {
    const { result } = renderHook(() => useLinks(), { wrapper: wrap });
    const a = vi.fn(), b = vi.fn();
    let offA = () => {}, offB = () => {};
    act(() => { offA = result.current.registerPaper(a); });
    act(() => { offB = result.current.registerPaper(b); });
    act(() => offA());
    act(() => result.current.jumpToPaper(span));
    expect(a).not.toHaveBeenCalled();
    expect(b).toHaveBeenCalledTimes(1);
    act(() => offB());
    act(() => result.current.jumpToPaper(span));
    expect(b).toHaveBeenCalledTimes(1);
  });

  it("hover state", () => {
    const { result } = renderHook(() => useLinks(), { wrapper: wrap });
    act(() => result.current.setHover("q"));
    expect(result.current.hover).toBe("q");
  });
});
