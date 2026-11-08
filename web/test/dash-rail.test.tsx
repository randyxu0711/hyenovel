import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import Rail from "../src/dash/Rail";
import { dotState, useSeen } from "../src/dash/useSeen";
import { setLang } from "../src/dash/i18n";
import { getThemeState, initThemes } from "../src/dash/theme";
import { olive } from "./dash-fixtures";
import type { Work } from "../src/dash/api";
import type { Talk } from "../src/dash/useTalk";

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

type Sess = { session: string; preview: string; versions?: [number, number] | null };
const fakeTalk = (sessions: Sess[] = [], extra: Record<string, unknown> = {}) => ({
  sessions: sessions.map(x => ({ started_at: 1, last_at: 1, turns: 1, character: null, version: null, legacy: false, ...x })),
  session: null as string | null, streaming: null as string | null, turns: [], open: vi.fn(), fresh: vi.fn(), ...extra,
}) as unknown as Talk;

describe("Rail(展開)", () => {
  const mount = (o: { current?: string | null; works?: Work[]; talk?: Talk; view?: "home" | "work" | "settings" } = {}) => {
    const p = { onOpen: vi.fn(), onNew: vi.fn(), onFind: vi.fn(), onChat: vi.fn(), onToggle: vi.fn() };
    const talk = o.talk ?? fakeTalk();
    const r = render(<MemoryRouter><Where /><Rail mode="open" works={o.works ?? WORKS} current={o.current ?? null}
      talk={talk} view={o.view ?? "home"} {...p} /></MemoryRouter>);
    return { ...p, ...r, talk };
  };
  it("頂列:收合;開一局聊天只有聊天組那顆 +;底:晝夜、設定", () => {
    const { onToggle, onNew, onChat } = mount();
    fireEvent.click(screen.getByRole("button", { name: "收合書架" }));
    expect(onToggle).toHaveBeenCalled();
    expect(screen.getAllByRole("button", { name: "開一局聊天" })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "開一局聊天" }));
    expect(onChat).toHaveBeenCalledWith(null);
    expect(onNew).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "設定" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "切換晝夜" })).toBeTruthy();
    expect(screen.queryByText("交一篇新的")).toBeNull();
  });
  it("列出作品標題,點了開那篇;目前那篇 aria-current;分析中那篇的點叫「分析中」", () => {
    const { onOpen } = mount({ current: "d1" });
    fireEvent.click(screen.getByRole("button", { name: /山/ }));
    expect(onOpen).toHaveBeenCalledWith("d2");
    expect(screen.getByRole("button", { name: /海/ }).getAttribute("aria-current")).toBe("true");
    expect(within(screen.getByRole("button", { name: /山/ })).getByRole("img").getAttribute("aria-label")).toBe("分析中");
  });
  it("看過後有更新的作品亮 fresh 點;沒開過的不亮", () => {
    localStorage.setItem("hyenovel.seen", JSON.stringify({ d3: 50 }));
    mount();
    expect(within(screen.getByRole("button", { name: /湖/ })).getByRole("img").getAttribute("aria-label")).toBe("有新東西");
    expect(within(screen.getByRole("button", { name: /海/ })).queryByRole("img")).toBeNull();
  });
  it("書架沒有說明性段落:按鈕外的字只有品牌", () => {
    const { container } = mount({ current: "d1", talk: fakeTalk([{ session: "a", preview: "第一句" }]) });
    expect(container.querySelector("p")).toBeNull();
    const texts: string[] = [];
    const walk = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      if (n.parentElement!.closest("button, output") === null) texts.push(n.textContent!.trim());
    }
    expect(texts.filter(Boolean)).toEqual(["Hyenovel", "聊天"]);
  });
  it("作品 ≤ 6 沒有篩選框;7 篇才有,輸入「山」只剩含「山」的", () => {
    const { unmount } = mount({ works: WORKS.concat([w("d4", "a"), w("d5", "b"), w("d6", "c")]) });
    expect(screen.queryByRole("searchbox")).toBeNull();
    unmount();
    mount({ works: WORKS.concat([w("d4", "a"), w("d5", "b"), w("d6", "c"), w("d7", "山路")]) });
    fireEvent.change(screen.getByRole("searchbox", { name: "篩選作品" }), { target: { value: "山" } });
    expect(screen.getAllByRole("button", { name: /^山/ })).toHaveLength(2);
    expect(screen.queryByRole("button", { name: /海/ })).toBeNull();
  });
  it("每列有時間字;curve 有兩點以上才畫指紋", () => {
    vi.spyOn(Date, "now").mockReturnValue(new Date(2026, 10, 2, 12).getTime());
    const today = new Date(2026, 10, 2, 8).getTime() / 1000;
    mount({ works: [w("d1", "海", { updated_at: today, curve: [0.2, 0.9] }), w("d2", "山", { updated_at: today, curve: [] })] });
    expect(within(screen.getByRole("button", { name: /海/ })).getByText("今天")).toBeTruthy();
    expect(screen.getByRole("button", { name: /海/ }).querySelector("svg.shelf-fp polyline")).toBeTruthy();
    expect(screen.getByRole("button", { name: /山/ }).querySelector("svg.shelf-fp")).toBeNull();
    vi.restoreAllMocks();
  });
  const SESS: Sess[] = [{ session: "a", preview: "一", versions: [4, 5] }, { session: "b", preview: "二", versions: [3, 3] },
    { session: "c", preview: "三", versions: null }, { session: "d", preview: "四" }, { session: "e", preview: "五" }];
  it("只有目前這篇展開局:最多 3 局 + 「還有 N 局」;點它全展開", () => {
    mount({ current: "d1", talk: fakeTalk(SESS) });
    const list = screen.getByRole("list", { name: "這篇的對話" });
    expect(screen.getAllByRole("list", { name: "這篇的對話" })).toHaveLength(1);
    expect(within(list).queryByRole("button", { name: /^四/ })).toBeNull();
    fireEvent.click(within(list).getByRole("button", { name: "還有 2 局" }));
    expect(within(list).getByRole("button", { name: /^五/ })).toBeTruthy();
    expect(within(list).queryByRole("button", { name: /還有/ })).toBeNull();
  });
  it("局列顯示第一句與 v4–5;同版只寫 v3;versions null 不寫", () => {
    mount({ current: "d1", talk: fakeTalk(SESS) });
    expect(screen.getByRole("button", { name: /^一/ }).textContent).toBe("一v4–5");
    expect(screen.getByRole("button", { name: /^二/ }).textContent).toBe("二v3");
    expect(screen.getByRole("button", { name: /^三/ }).textContent).toBe("三");
  });
  it("點局 → talk.open(id);目前這局 aria-current;串流中點 → 不呼叫", () => {
    const t = fakeTalk(SESS, { session: "b" });
    const { unmount } = mount({ current: "d1", talk: t });
    expect(screen.getByRole("button", { name: /^二/ }).getAttribute("aria-current")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: /^一/ }));
    expect(t.open).toHaveBeenCalledWith("a");
    unmount();
    const busy = fakeTalk(SESS, { streaming: "x" });
    mount({ current: "d1", talk: busy });
    fireEvent.click(screen.getByRole("button", { name: /^一/ }));
    fireEvent.click(screen.getByRole("button", { name: "開一局" }));
    expect(busy.open).not.toHaveBeenCalled();
    expect(busy.fresh).not.toHaveBeenCalled();
  });
  it("「開一局」→ talk.fresh()", () => {
    const t = fakeTalk(SESS);
    mount({ current: "d1", talk: t });
    fireEvent.click(screen.getByRole("button", { name: "開一局" }));
    expect(t.fresh).toHaveBeenCalled();
  });
  it("晝夜快捷鍵:一按就翻到另一邊", () => {
    mount();
    const before = getThemeState().mode;
    fireEvent.click(screen.getByRole("button", { name: "切換晝夜" }));
    expect(getThemeState().mode).not.toBe(before);
    fireEvent.click(screen.getByRole("button", { name: "切換晝夜" }));
    expect(getThemeState().mode).toBe(before);
  });
  it("設定鍵導到 /settings;在 /settings 時 aria-current=page", () => {
    const { unmount } = mount();
    expect(screen.getByRole("button", { name: "設定" }).getAttribute("aria-current")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "設定" }));
    expect(screen.getByTestId("loc").textContent).toBe("/settings");
    unmount();
    mount({ view: "settings" });
    expect(screen.getByRole("button", { name: "設定" }).getAttribute("aria-current")).toBe("page");
  });
});

describe("Rail(窄條)", () => {
  const mount = (o: { current?: string | null; works?: Work[]; talk?: Talk } = {}) => {
    const p = { onOpen: vi.fn(), onNew: vi.fn(), onFind: vi.fn(), onChat: vi.fn(), onToggle: vi.fn() };
    const talk = o.talk ?? fakeTalk();
    const r = render(<MemoryRouter><Where /><Rail mode="rail" works={o.works ?? WORKS} current={o.current ?? null}
      talk={talk} view="work" {...p} /></MemoryRouter>);
    return { ...p, ...r, talk };
  };
  it("由上而下:展開、開一局聊天、找作品、目前這篇、晝夜、設定;不列作品標題", () => {
    mount({ current: "d1" });
    const names = screen.getAllByRole("button").map(b => b.getAttribute("aria-label"));
    expect(names).toEqual(["展開書架", "開一局聊天", "找作品", "海", "切換晝夜", "設定"]);
    for (const t of ["山", "湖"]) expect(screen.queryByText(t)).toBeNull();
  });
  it("目前這篇顯示標題第一個字;沒有 current 就沒有這顆", () => {
    const { unmount } = mount({ current: "d1", works: [w("d1", "海邊的人")] });
    expect(screen.getByRole("button", { name: "海邊的人" }).textContent).toBe("海");
    unmount();
    mount();
    expect(screen.getAllByRole("button")).toHaveLength(5);
  });
  it("目前這篇分析中 → 有跳動點", () => {
    mount({ current: "d2" });
    expect(within(screen.getByRole("button", { name: "山" })).getByRole("img").getAttribute("aria-label")).toBe("分析中");
  });
  it("點目前這篇 → 浮層列局;點局換局並關;Esc 關、焦點回鍵", () => {
    const t = fakeTalk([{ session: "a", preview: "一" }]);
    mount({ current: "d1", talk: t });
    fireEvent.click(screen.getByRole("button", { name: "海" }));
    const pop = screen.getByRole("dialog", { name: "海" });
    fireEvent.keyDown(within(pop).getByRole("button", { name: /^一/ }), { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "海" }));
    fireEvent.click(screen.getByRole("button", { name: "海" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /^一/ }));
    expect(t.open).toHaveBeenCalledWith("a");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
  it("別篇有新東西 → 找作品鍵上有點;只有目前這篇新 → 沒有", () => {
    localStorage.setItem("hyenovel.seen", JSON.stringify({ d1: 50 }));
    const { unmount } = mount({ current: "d3" });
    expect(within(screen.getByRole("button", { name: "找作品" })).getByRole("img").getAttribute("aria-label")).toBe("有新東西");
    unmount();
    mount({ current: "d1" });
    expect(within(screen.getByRole("button", { name: "找作品" })).queryByRole("img")).toBeNull();
  });
  it("找作品 → onFind", () => {
    const { onFind } = mount();
    fireEvent.click(screen.getByRole("button", { name: "找作品" }));
    expect(onFind).toHaveBeenCalled();
  });
});
