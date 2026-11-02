import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, act, fireEvent } from "@testing-library/react";
import { useEffect } from "react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import Paper, { DRAW_MS, segments, type Mark } from "../src/dash/Paper";
import { cpLength, cpSlice } from "../src/dash/cp";
import { setLang } from "../src/dash/i18n";
import { LinksProvider, useLinks, type Links } from "../src/dash/links";
import { CharactersProvider, makeCharacters } from "../src/dash/useCharacters";
import { setPaperFlow } from "../src/dash/paperFlow";
import type { Character } from "../src/dash/api";
import { hyena, buffalo, deer, ch } from "./dash-fixtures";

const odd = { ...ch("fox", "slow", "狐", "Fox"), mark: "zigzag" as unknown as Character["mark"] };
let links: Links;
function Probe() { const l = useLinks(); useEffect(() => { links = l; }); return null; }

const mount = (text: string, marks: Mark[] = [], extra: { drawing?: string; title?: string; old?: boolean; obs?: { start: number; end: number }[] } = {}) => {
  setLang("zh-Hant");
  const onBring = vi.fn();
  const r = render(
    <CharactersProvider value={makeCharacters([hyena, buffalo, deer, odd], "hyena")}>
      <LinksProvider>
        <Probe />
        <Paper text={text} title={extra.title ?? "海"} marks={marks} drawing={extra.drawing} onBring={onBring} old={extra.old} obs={extra.obs} />
      </LinksProvider>
    </CharactersProvider>);
  return { ...r, onBring };
};
const mk = (start: number, end: number, character = "hyena"): Mark => ({ start, end, character, id: `${start}-${end}-${character}` });
const marks = () => [...document.querySelectorAll<HTMLElement>(".dash-mark")];
const select = (node: Node, len: number) => {
  const range = document.createRange();
  range.setStart(node, 0); range.setEnd(node, len);
  const sel = document.getSelection()!;
  sel.removeAllRanges(); sel.addRange(range);
  act(() => { document.dispatchEvent(new Event("selectionchange")); });
};

beforeEach(() => { Element.prototype.scrollIntoView = vi.fn(); act(() => setPaperFlow("v")); });
afterEach(() => { vi.useRealTimers(); document.getSelection()?.removeAllRanges(); });

describe("segments", () => {
  it("每段的起點是 code point 位移,對得回原文(含 𠀋)", () => {
    const text = "𠀋頭一段。\n\n　　第二段𠀋有字。\r\n第三段。\n";
    const segs = segments(text, "別的標題");
    expect(segs.map(s => s.text)).toEqual(["𠀋頭一段。", "第二段𠀋有字。", "第三段。"]);
    expect(segs.map(s => s.start)).toEqual([0, 9, 18]);
    for (const s of segs) expect(cpSlice(text, s.start, s.start + cpLength(s.text))).toBe(s.text);
  });
  it("首段只是標題就略過(位移照舊)", () => {
    const segs = segments("《海》\n\n第一段。", "海");
    expect(segs).toEqual([{ start: 5, text: "第一段。" }]);
  });
  it("只有一段時,就算是標題也留著", () => {
    expect(segments("海", "海")).toEqual([{ start: 0, text: "海" }]);
  });
});

describe("Paper", () => {
  it("一個痕跡渲染成一個 .dash-mark;不分角色同一種線,沒有 data-mark", () => {
    mount("海很深。潮水回來。", [mk(0, 3), mk(4, 6, "buffalo")]);
    expect(marks()).toHaveLength(2);
    expect(marks()[0].textContent).toBe("海很深");
    expect(marks()[0].dataset.id).toBe("0-3-hyena");
    expect(marks().every(m => m.dataset.mark === undefined && !m.style.getPropertyValue("--dash-mark"))).toBe(true);
  });
  it("跨兩段的痕跡畫成兩截,同一個 data-id", () => {
    mount("第一段尾巴\n第二段頭", [mk(3, 8)]);
    const ms = marks();
    expect(ms.map(m => m.textContent)).toEqual(["尾巴", "第二"]);
    expect(new Set(ms.map(m => m.dataset.id)).size).toBe(1);
    expect(ms[0].closest("p")).not.toBe(ms[1].closest("p"));
  });
  it("同一句兩處出現,只標 den 給的那一處", () => {
    mount("潮水。\n潮水。", [mk(4, 6)]);
    const ps = document.querySelectorAll(".dash-paper p");
    expect(ps[0].querySelector(".dash-mark")).toBeNull();
    expect(ps[1].querySelector(".dash-mark")!.textContent).toBe("潮水");
  });
  it("位移用 code point:𠀋 後面的痕跡不偏", () => {
    mount("𠀋海很深", [mk(1, 3)]);
    expect(marks()[0].textContent).toBe("海很");
  });
  it("正在畫的痕跡多 is-drawing", () => {
    mount("海很深。潮水。", [mk(0, 2), mk(4, 6, "buffalo")], { drawing: "4-6-buffalo" });
    expect(marks().map(m => m.classList.contains("is-drawing"))).toEqual([false, true]);
  });
  it("滑過(setHover)那句 → 對應痕跡 is-hover;只差標點也算", () => {
    mount("海很深,潮水。", [mk(0, 6)]);
    act(() => links.setHover("海很深。潮水"));
    expect(marks()[0].classList.contains("is-hover")).toBe(true);
    act(() => links.setHover(null));
    expect(marks()[0].classList.contains("is-hover")).toBe(false);
  });
  it("滑過帶位置 → 只亮那個位置的痕跡(同一句出現兩處)", () => {
    mount("海。海。", [mk(0, 1), mk(2, 3, "buffalo")]);
    act(() => links.setHover("海", 2));
    expect(marks().map(m => m.classList.contains("is-hover"))).toEqual([false, true]);
  });
  it("點痕跡 → jumpToTalk(那句原文)", () => {
    mount("海很深。", [mk(0, 3)]);
    const talk = vi.fn(() => true);
    act(() => { links.registerTalk(talk); });
    fireEvent.click(marks()[0]);
    expect(talk).toHaveBeenCalledWith("海很深");
  });
  it("jumpToPaper → 那段捲過來並閃一下,1.4s 後收掉", () => {
    vi.useFakeTimers();
    mount("第一段。\n第二段。\n第三段。", []);
    act(() => links.jumpToPaper({ quote: "第二段", start: 5, end: 8 }));
    const p = screen.getByText("第二段。");
    expect(p.scrollIntoView).toHaveBeenCalled();
    expect(p.classList.contains("is-flash")).toBe(true);
    act(() => { vi.advanceTimersByTime(1500); });
    expect(screen.getByText("第二段。").classList.contains("is-flash")).toBe(false);
  });
  it("段落閃動不重掛載段落(正在畫的痕跡不重播、選取不丟);再跳一次也閃", () => {
    mount("第一段。\n海很深。", [mk(5, 8)], { drawing: "5-8-hyena" });
    const p = screen.getByText(/很深/).closest("p")!, m = marks()[0];
    act(() => links.jumpToPaper({ quote: "海很深", start: 5, end: 8 }));
    expect(p.classList.contains("is-flash")).toBe(true);
    const flash = p.querySelector(".paper-flash");
    act(() => links.jumpToPaper({ quote: "海很深", start: 5, end: 8 }));
    expect(screen.getByText(/很深/).closest("p")).toBe(p);
    expect(marks()[0]).toBe(m);
    expect(p.querySelector(".paper-flash")).not.toBe(flash);   // 只換閃動那層,動畫重播
  });
  it("jumpToPaper 的位置對不上這張稿(別版的位置)→ 不跳", () => {
    mount("第一段。\n第二段。", []);
    act(() => links.jumpToPaper({ quote: "第三段", start: 5, end: 8 }));
    expect(document.querySelector(".is-flash")).toBeNull();
  });
  it("jumpToPaper 對不到位置(start 為 null)什麼都不做", () => {
    mount("第一段。", []);
    act(() => links.jumpToPaper({ quote: "不在", start: null, end: null }));
    expect(document.querySelector(".is-flash")).toBeNull();
  });
  it("選字 → 出現「帶進對話」,點了送出引文並清掉", () => {
    const { onBring } = mount("第一段。\n第二段。");
    select(screen.getByText("第一段。").firstChild!, 3);
    fireEvent.click(screen.getByRole("button", { name: "帶進對話" }));
    expect(onBring).toHaveBeenCalledWith("第一段");
    expect(screen.queryByRole("button", { name: "帶進對話" })).toBeNull();
  });
  it("超過 400 字:鈕 disabled 並提示", () => {
    mount("字".repeat(450));
    select(screen.getByText("字".repeat(450)).firstChild!, 450);
    expect((screen.getByRole("button", { name: "帶進對話" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("選短一點(400 字內)")).toBeTruthy();
  });
});

describe("筆畫長度", () => {
  it("CSS 的畫線動畫長度取自 DRAW_MS(--dash-draw),且至少 600ms", () => {
    const css = readFileSync(join(__dirname, "../src/dash/dash.css"), "utf8");
    expect(css).toMatch(/\.dash-mark\.is-drawing\{animation:dash-mark-draw var\(--dash-draw\)/);
    expect(DRAW_MS).toBeGreaterThanOrEqual(600);
  });
});

describe("Paper 排法與分頁", () => {
  // jsdom 沒版面:量測容器用「頁內字數 ≤ N」假裝
  const fakePage = (n: number) => {
    const sw = vi.spyOn(HTMLElement.prototype, "scrollWidth", "get").mockImplementation(function (this: HTMLElement) {
      return this.classList.contains("paper-measure") ? cpLength((this.textContent ?? "").replace(/\s/g, "")) : 0;
    });
    const cw = vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockImplementation(function (this: HTMLElement) {
      return this.classList.contains("paper-measure") ? n : 0;
    });
    return () => { sw.mockRestore(); cw.mockRestore(); };
  };
  const pages = () => [...document.querySelectorAll<HTMLElement>(".paper-page")];

  it("預設直排:data-flow=v,一頁,頁碼 1", () => {
    const { container } = mount("海很深。");
    expect(container.querySelector("article")!.dataset.flow).toBe("v");
    expect(pages()).toHaveLength(1);
    expect(pages()[0].querySelector(".paper-folio")!.textContent).toBe("1");
  });
  it("切橫排 → data-flow=h,沒有分頁", () => {
    const { container } = mount("海很深。");
    act(() => setPaperFlow("h"));
    expect(container.querySelector("article")!.dataset.flow).toBe("h");
    expect(pages()).toHaveLength(0);
  });
  it("直排時 40 直立,橫排不包", () => {
    const { container } = mount("走了 40 年");
    expect(container.querySelector(".paper-tcy")!.textContent).toBe("40");
    act(() => setPaperFlow("h"));
    expect(container.querySelector(".paper-tcy")).toBeNull();
  });
  it("長段跨頁:續段 data-start 往後推、data-cont;跨頁的痕跡兩頁都畫", () => {
    const restore = fakePage(4);
    mount("一二三四五六", [mk(2, 6)]);
    restore();
    expect(pages()).toHaveLength(2);
    const ps = pages().map(pg => pg.querySelector("p")!);
    expect(ps.map(p => p.dataset.start)).toEqual(["0", "4"]);
    expect(ps[1].hasAttribute("data-cont")).toBe(true);
    expect(marks().map(m => m.textContent)).toEqual(["三四", "五六"]);
  });
  it("jumpToPaper 跳到續段那一頁的段", () => {
    const restore = fakePage(4);
    mount("一二三四五六");
    restore();
    act(() => links.jumpToPaper({ quote: "五六", start: 4, end: 6 }));
    expect(pages()[1].querySelector("p")!.classList.contains("is-flash")).toBe(true);
  });
  it("舊版:不畫陪讀者的線、紙有 is-old", () => {
    const { container } = mount("海很深。", [mk(0, 3)], { old: true });
    expect(marks()).toHaveLength(0);
    expect(container.querySelector(".is-old")).not.toBeNull();
  });
  it("觀察直線:obs 的位置畫 .paper-ob;同處有痕跡時兩種都在", () => {
    const { container } = mount("海很深。潮水。", [mk(0, 2)], { obs: [{ start: 1, end: 3 }, { start: 4, end: 6 }] });
    const obs = [...container.querySelectorAll(".paper-ob")].map(e => e.textContent);
    expect(obs.join("")).toBe("很深潮水");
    expect(marks().map(m => m.querySelector(".paper-ob")?.textContent).filter(Boolean)).toEqual(["很"]);
  });
});

describe("直排頁的 CSS", () => {
  const css = readFileSync(join(__dirname, "../src/dash/dash.css"), "utf8");
  it("直排欄框撐滿頁寬(不然沒滿的頁會擠在左邊,直排應從右起)", () => {
    expect(css).toMatch(/\.dash \.paper-cols\{[^}]*width:100%/);
  });
  it("頁碼不能被選進引文", () => {
    expect(css).toMatch(/\.dash \.paper-folio\{[^}]*user-select:none/);
  });
});
