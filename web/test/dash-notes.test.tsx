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
  version: 2, analysis_version: 2, notes_version: 2, beats: [], motifs: [], notes: null, drift: null, ...o,
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
  it("開頭只標版本與「讀伴看不到」;各點有類型、標題、說明、問題", () => {
    mount(map({ notes }));
    const meta = document.querySelector(".notes-meta")!;
    expect(meta.querySelector(".dash-dm")!.textContent).toBe("v2");
    expect(meta.getAttribute("title")).toBe("讀伴看不到這些筆記");
    expect(document.body.textContent).not.toContain("冷讀者");
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
    expect(b.getAttribute("title")).toBe("v2 沒有這句");
    fireEvent.click(b);
    expect(on).not.toHaveBeenCalled();
  });
  it.each([
    ["notes-running", "筆記撰寫中。"],
    ["running", "筆記撰寫中。"],
    ["notes-stopped", "筆記已中斷。"],
    ["stopped", "筆記已中斷。"],
    ["ready", "沒有筆記"],
    ["none", "尚未分析"],
  ])("沒有筆記、作品 %s → %s", (state, text) => {
    mount(map(), state);
    expect(screen.getByText(text)).toBeTruthy();
  });
  it("對位資料抓不到:顯示錯誤,不停在載入中", () => {
    mount(null, "ready", vi.fn(), "den-down");
    expect(screen.getByText("無法連線至本機 den，請確認是否在執行。")).toBeTruthy();
    expect(screen.queryByText("載入中……")).toBeNull();
  });
  it("對位資料還沒到:載入中", () => {
    mount(null);
    expect(screen.getByText("載入中……")).toBeTruthy();
  });
});

describe("筆記眉頭的對照入口", () => {
  it("notes older than viewed version → compare button calls onCompare", () => {
    setLang("zh-Hant");
    const on = vi.fn();
    render(<LinksProvider><NotesTab map={map({ version: 3, notes_version: 2, notes })} state="ready" onCompare={on} /></LinksProvider>);
    fireEvent.click(screen.getByRole("button", { name: "對照 v2" }));
    expect(on).toHaveBeenCalledWith(2);
  });
  it("same version → no button", () => {
    setLang("zh-Hant");
    render(<LinksProvider><NotesTab map={map({ notes })} state="ready" onCompare={vi.fn()} /></LinksProvider>);
    expect(screen.queryByRole("button", { name: /對照/ })).toBeNull();
  });
});
