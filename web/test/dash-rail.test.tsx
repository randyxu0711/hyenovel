import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import Rail from "../src/dash/Rail";
import WorksMenu from "../src/dash/WorksMenu";
import { dotState, useSeen } from "../src/dash/useSeen";
import { setLang } from "../src/dash/i18n";
import { initThemes, getThemeState } from "../src/dash/theme";
import { olive } from "./dash-fixtures";
import type { Work } from "../src/dash/api";

const w = (slug: string, title: string, extra: Partial<Work> = {}): Work =>
  ({ slug, title, version: 1, chars: 100, updated_at: 100, state: "ready", ...extra });
function Where() { return <output data-testid="loc">{useLocation().pathname}</output>; }
const WORKS = [w("d1", "海", { updated_at: 500 }), w("d2", "山", { state: "running" }), w("d3", "湖")];

beforeEach(() => { setLang("zh-Hant"); localStorage.clear(); initThemes([olive], "olive"); });

describe("dotState", () => {
  it("分析中 → busy,即使沒看過", () => {
    expect(dotState(w("a", "a", { state: "running" }), null)).toBe("busy");
    expect(dotState(w("a", "a", { state: "notes-running" }), 999)).toBe("busy");
  });
  it("看過之後有更新 → fresh", () => {
    expect(dotState(w("a", "a", { updated_at: 200 }), 100)).toBe("fresh");
  });
  it("看過後沒新東西 → none", () => {
    expect(dotState(w("a", "a", { updated_at: 100 }), 100)).toBe("none");
    expect(dotState(w("a", "a", { updated_at: 50 }), 100)).toBe("none");
  });
  it("沒打開過(null)→ none,第一次使用不會全亮", () => {
    expect(dotState(w("a", "a", { updated_at: 999 }), null)).toBe("none");
  });
});

describe("useSeen", () => {
  function Probe() {
    const { seen, markSeen } = useSeen();
    return <button onClick={() => markSeen("d1")}>{String(seen("d1"))}</button>;
  }
  it("沒開過是 null;markSeen 存 epoch 秒並讓所有使用者更新", () => {
    vi.spyOn(Date, "now").mockReturnValue(1_700_000_000_000);
    render(<Probe />);
    expect(screen.getByRole("button").textContent).toBe("null");
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByRole("button").textContent).toBe("1700000000");
    expect(JSON.parse(localStorage.getItem("hyenovel.seen")!)).toEqual({ d1: 1_700_000_000 });
    vi.restoreAllMocks();
  });
});

describe("Rail", () => {
  const mount = (collapsed: boolean, current: string | null = null, works = WORKS) => {
    const p = { onOpen: vi.fn(), onNew: vi.fn() };
    const r = render(<MemoryRouter><Where /><Rail collapsed={collapsed} works={works} current={current} {...p} /></MemoryRouter>);
    return { ...p, ...r };
  };
  it("展開:列出作品標題,點了開那篇;新對話鈕", () => {
    const { onOpen, onNew } = mount(false);
    for (const t of ["海", "山", "湖"]) expect(screen.getByText(t)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /山/ }));
    expect(onOpen).toHaveBeenCalledWith("d2");
    fireEvent.click(screen.getByRole("button", { name: "新對話" }));
    expect(onNew).toHaveBeenCalled();
  });
  it("展開:目前那篇標 aria-current;分析中那篇有點,可及名稱是狀態", () => {
    mount(false, "d1");
    expect(screen.getByRole("button", { name: "海" }).getAttribute("aria-current")).toBe("true");
    expect(screen.getByRole("button", { name: /山/ }).querySelector('[role="img"]')!.getAttribute("aria-label")).toBe("分析中");
  });
  it("收起:不出現任何作品標題,只剩有名字的鍵(作品、設定、切換晝夜、新對話)", () => {
    const { onNew } = mount(true, "d1");
    for (const t of ["海", "山", "湖"]) expect(screen.queryByText(t)).toBeNull();
    for (const n of ["作品", "設定", "切換晝夜"]) expect(screen.getByRole("button", { name: n })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "新對話" }));
    expect(onNew).toHaveBeenCalled();
  });
  it("左欄沒有說明性段落:文字只有作品標題與按鈕名稱", () => {
    const { container } = mount(false);
    expect(container.querySelector("p")).toBeNull();
    const texts: string[] = [];
    const walk = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      if (n.parentElement!.closest("button, output") === null) texts.push(n.textContent!.trim());
    }
    expect(texts.filter(Boolean)).toEqual(["hyenovel"]);
  });
  it("看過後有更新的作品亮 fresh 點;沒開過的不亮", () => {
    localStorage.setItem("hyenovel.seen", JSON.stringify({ d3: 50 }));
    mount(false);
    expect(within(screen.getByRole("button", { name: /湖/ })).getByRole("img").getAttribute("aria-label")).toBe("有新東西");
    expect(within(screen.getByRole("button", { name: /海/ })).queryByRole("img")).toBeNull();
  });
  it("設定鍵導到 /settings(展開、收起都有)", () => {
    mount(false);
    fireEvent.click(screen.getByRole("button", { name: "設定" }));
    expect(screen.getByTestId("loc").textContent).toBe("/settings");
  });
  it("晝夜鍵呼叫 toggleDayNight", () => {
    mount(true);
    const before = getThemeState().mode;
    fireEvent.click(screen.getByRole("button", { name: "切換晝夜" }));
    expect(getThemeState().mode).toBe(before === "dark" ? "light" : "dark");
  });
  it("收起時點「作品」開浮層:列標題與狀態文字;Esc 關閉;選一篇開它並關閉", () => {
    localStorage.setItem("hyenovel.seen", JSON.stringify({ d1: 50 }));
    const { onOpen } = mount(true, "d3");
    fireEvent.click(screen.getByRole("button", { name: "作品" }));
    const menu = screen.getByRole("dialog", { name: "作品" });
    expect(within(menu).getByText("有新東西")).toBeTruthy();   // 海 updated 500 > seen 50
    expect(within(menu).getByText("分析中")).toBeTruthy();
    expect(within(menu).getByRole("button", { name: /湖/ }).getAttribute("aria-current")).toBe("true");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "作品" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /山/ }));
    expect(onOpen).toHaveBeenCalledWith("d2");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("WorksMenu", () => {
  const anchor = document.createElement("button");
  const mount = () => {
    const p = { onOpen: vi.fn(), onSubmitNew: vi.fn(), onClose: vi.fn() };
    render(<WorksMenu anchor={anchor} works={WORKS} current={null} {...p} />);
    return p;
  };
  it("點外面關閉;點錨本身不算外面(交給錨自己 toggle)", () => {
    const p = mount();
    fireEvent.mouseDown(anchor);
    expect(p.onClose).not.toHaveBeenCalled();
    fireEvent.mouseDown(document.body);
    expect(p.onClose).toHaveBeenCalled();
  });
  it("「交一篇新的」呼叫 onSubmitNew 並關閉", () => {
    const p = mount();
    fireEvent.click(screen.getByRole("button", { name: "交一篇新的" }));
    expect(p.onSubmitNew).toHaveBeenCalled();
    expect(p.onClose).toHaveBeenCalled();
  });
});
