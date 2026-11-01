import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, act, fireEvent } from "@testing-library/react";
import { useEffect } from "react";
import Paper, { segments, type Mark } from "../src/dash/Paper";
import { cpLength, cpSlice } from "../src/dash/cp";
import { setLang } from "../src/dash/i18n";
import { LinksProvider, useLinks, type Links } from "../src/dash/links";
import { CharactersProvider, makeCharacters } from "../src/dash/useCharacters";
import { getThemeState } from "../src/dash/theme";
import type { Character } from "../src/dash/api";
import { hyena, buffalo, deer, ch } from "./dash-fixtures";

const odd = { ...ch("fox", "slow", "狐", "Fox"), mark: "zigzag" as unknown as Character["mark"] };
let links: Links;
function Probe() { const l = useLinks(); useEffect(() => { links = l; }); return null; }

const mount = (text: string, marks: Mark[] = [], extra: { drawing?: string; title?: string } = {}) => {
  setLang("zh-Hant");
  const onBring = vi.fn();
  const r = render(
    <CharactersProvider value={makeCharacters([hyena, buffalo, deer, odd], "hyena")}>
      <LinksProvider>
        <Probe />
        <Paper text={text} title={extra.title ?? "海"} marks={marks} drawing={extra.drawing} onBring={onBring} />
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

beforeEach(() => { Element.prototype.scrollIntoView = vi.fn(); });
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
  it("一個痕跡渲染成一個 .dash-mark,筆跡依角色,顏色是角色在目前明暗的 fill", () => {
    mount("海很深。潮水回來。", [mk(0, 3)]);
    expect(marks()).toHaveLength(1);
    const m = marks()[0];
    expect(m.textContent).toBe("海很深");
    expect(m.dataset.mark).toBe("pencil");
    expect(m.dataset.id).toBe("0-3-hyena");
    expect(m.style.getPropertyValue("--dash-mark")).toBe(hyena.colors[getThemeState().mode].fill);
  });
  it.each([["buffalo", "highlighter"], ["deer", "circle"], ["fox", "pencil"]])("角色 %s → data-mark=%s", (who, kind) => {
    mount("海很深。", [mk(0, 2, who)]);
    expect(marks()[0].dataset.mark).toBe(kind);
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
