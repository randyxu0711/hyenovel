import { describe, it, expect, vi, beforeEach } from "vitest";
import { useEffect } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import NotesTab from "../src/dash/NotesTab";
import type { Span, WorkMap } from "../src/dash/api";
import { setLang } from "../src/dash/i18n";
import { LinksProvider, useLinks } from "../src/dash/links";

function PaperSpy({ on }: { on: (s: Span) => void }) {
  const { registerPaper } = useLinks();
  useEffect(() => registerPaper(on), [registerPaper, on]);
  return null;
}
function HoverSpy() { const l = useLinks(); return <output data-testid="hover" data-at={l.hoverAt ?? ""}>{l.hover ?? ""}</output>; }

const map = (o: Partial<WorkMap> = {}): WorkMap => ({
  version: 2, analysis_version: 2, notes_version: 2, beats: [], motifs: [], notes: null, ...o,
});
const notes: WorkMap["notes"] = {
  read: "讀到的", one_line: "一件事",
  points: [
    { kind: "confused", title: "鑰匙突然出現", body: "前面沒提過。", question: "早一點出現?", spans: [{ quote: "她摸出鑰匙", start: 4, end: 9 }] },
    { kind: "moved", title: "泥的溫度", body: "觸覺開場。", question: null, spans: [{ quote: "泥是溫的", start: null, end: null }] },
  ],
};
function mount(m: WorkMap | null, state = "ready", on = vi.fn(), error: string | null = null) {
  render(<LinksProvider><PaperSpy on={on} /><HoverSpy /><NotesTab map={m} state={state} error={error} /></LinksProvider>);
  return on;
}

beforeEach(() => setLang("zh-Hant"));

describe("筆記分頁", () => {
  it("開頭說是冷讀者讀完第 N 版留下的、陪讀者看不到;各點有類型、標題、說明、問題", () => {
    mount(map({ notes }));
    expect(screen.getByText("冷讀者讀完第 2 版留下的筆記。陪讀者看不到這些。")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "鑰匙突然出現" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "泥的溫度" })).toBeTruthy();
    expect(screen.getByText("卡住的")).toBeTruthy();
    expect(screen.getByText("前面沒提過。")).toBeTruthy();
    expect(screen.getByText("早一點出現?")).toBeTruthy();
  });
  it("引文是按鈕:滑過設 hover、點了跳到稿", () => {
    const on = mount(map({ notes }));
    const b = screen.getByRole("button", { name: "「她摸出鑰匙」" });
    fireEvent.mouseEnter(b);
    expect(screen.getByTestId("hover").textContent).toBe("她摸出鑰匙");
    expect(screen.getByTestId("hover").dataset.at).toBe("4");
    fireEvent.mouseLeave(b);
    expect(screen.getByTestId("hover").textContent).toBe("");
    fireEvent.click(b);
    expect(on).toHaveBeenCalledWith({ quote: "她摸出鑰匙", start: 4, end: 9 });
  });
  it("這版對不到的引文是灰的、有說明,點了不跳", () => {
    const on = mount(map({ notes }));
    const b = screen.getByRole("button", { name: "「泥是溫的」" });
    expect(b.getAttribute("title")).toBe("這句在第 2 版找不到");
    fireEvent.click(b);
    expect(on).not.toHaveBeenCalled();
  });
  it.each([
    ["notes-running", "筆記還在寫。"],
    ["running", "筆記還在寫。"],
    ["notes-stopped", "筆記停住了。"],
    ["stopped", "筆記停住了。"],
    ["ready", "這篇是舊版流程讀的,沒有筆記。"],
    ["none", "還沒分析,所以還沒有筆記。"],
  ])("沒有筆記、作品 %s → %s", (state, text) => {
    mount(map(), state);
    expect(screen.getByText(text)).toBeTruthy();
  });
  it("對位資料抓不到:顯示錯誤,不停在載入中", () => {
    mount(null, "ready", vi.fn(), "den-down");
    expect(screen.getByText("連不上本機的 den,請確認它有在跑。")).toBeTruthy();
    expect(screen.queryByText("載入中……")).toBeNull();
  });
  it("對位資料還沒到:載入中", () => {
    mount(null);
    expect(screen.getByText("載入中……")).toBeTruthy();
  });
});
