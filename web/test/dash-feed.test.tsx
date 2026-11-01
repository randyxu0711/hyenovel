import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import Feed from "../src/dash/Feed";
import { api, DashError } from "../src/dash/api";
import { setLang } from "../src/dash/i18n";

afterEach(() => vi.restoreAllMocks());

function mount(est: object | null = null) {
  setLang("zh-Hant");
  vi.spyOn(api, "estimate").mockResolvedValue(est as never);
  const onClose = vi.fn(), onSubmitted = vi.fn();
  render(<Feed onClose={onClose} onSubmitted={onSubmitted} />);
  return { onClose, onSubmitted };
}
const type = (v: string) => fireEvent.change(screen.getByRole("textbox", { name: "稿子" }), { target: { value: v } });

describe("Feed", () => {
  it("是有名字的 modal,開啟時焦點在稿子欄,Esc 關閉", () => {
    const { onClose } = mount();
    const d = screen.getByRole("dialog", { name: "捲進一張新稿" });
    expect(d.getAttribute("aria-modal")).toBe("true");
    expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "稿子" }));
    fireEvent.keyDown(d, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
  it("預估為 null 時顯示第一次分析的說明", async () => {
    mount(null);
    type("一段稿子");
    expect(await screen.findByText("第一次分析,還沒有預估。")).toBeTruthy();
    expect(screen.getByText("4 字")).toBeTruthy();
  });
  it("有預估時顯示分鐘數", async () => {
    mount({ seconds: 300, output_tokens: 1, basis: 2 });
    type("一段稿子");
    expect(await screen.findByText("預估約 5 分鐘")).toBeTruthy();
  });
  it("主按鈕寫明會用訂閱額度;沒有稿時不能按", () => {
    mount();
    const b = screen.getByRole("button", { name: "交稿並開始分析(會用你的訂閱額度)" }) as HTMLButtonElement;
    expect(b.disabled).toBe(true);
    type("稿");
    expect(b.disabled).toBe(false);
  });
  it("送出:submit 後開 job 並通知", async () => {
    const { onSubmitted } = mount();
    vi.spyOn(api, "submit").mockResolvedValue({ slug: "d3", title: "t", version: 1, new_version: true, reused: false });
    const start = vi.spyOn(api, "startJob").mockResolvedValue({ job_id: 7 });
    type("稿");
    fireEvent.click(screen.getByRole("button", { name: /交稿並開始分析/ }));
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledWith("d3", false));
    expect(start).toHaveBeenCalledWith("d3");
  });
  it("reused 但那篇還沒分析(state none/stopped):補開 job", async () => {
    const { onSubmitted } = mount();
    vi.spyOn(api, "submit").mockResolvedValue({ slug: "d1", title: "t", version: 1, new_version: false, reused: true });
    vi.spyOn(api, "work").mockResolvedValue({ slug: "d1", title: "t", version: 1, text: "", state: "none", job_id: null, notes_ready: false, versions: [1] });
    const start = vi.spyOn(api, "startJob").mockResolvedValue({ job_id: 3 });
    type("稿");
    fireEvent.click(screen.getByRole("button", { name: /交稿並開始分析/ }));
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledWith("d1", true));
    expect(start).toHaveBeenCalledWith("d1");
  });
  it("有稿時點遮罩不會丟掉;Esc 先問,可繼續編輯或丟掉", () => {
    const { onClose } = mount();
    type("寫到一半");
    fireEvent.mouseDown(screen.getByRole("dialog").parentElement!);
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "繼續編輯" }));
    expect(screen.queryByRole("button", { name: "丟掉" })).toBeNull();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "丟掉" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
  it("確認中:焦點進到「繼續編輯」,Esc 等於繼續編輯(不丟稿),焦點回稿子欄,Tab 不離開對話框", () => {
    const { onClose } = mount();
    type("寫到一半");
    const d = screen.getByRole("dialog");
    fireEvent.keyDown(d, { key: "Escape" });
    const keepBtn = screen.getByRole("button", { name: "繼續編輯" });
    expect(document.activeElement).toBe(keepBtn);
    fireEvent.keyDown(d, { key: "Tab", shiftKey: true });   // 往前:不該跑出對話框
    expect(d.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(d, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "丟掉" })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "稿子" }));
    expect((screen.getByRole("textbox", { name: "稿子" }) as HTMLTextAreaElement).value).toBe("寫到一半");
  });
  it("沒有稿時點遮罩直接關", () => {
    const { onClose } = mount();
    fireEvent.mouseDown(screen.getByRole("dialog").parentElement!);
    expect(onClose).toHaveBeenCalled();
  });
  it("reused 且已分析完(ready/running/stale):不呼叫 startJob", async () => {
    const { onSubmitted } = mount();
    vi.spyOn(api, "submit").mockResolvedValue({ slug: "d1", title: "t", version: 1, new_version: false, reused: true });
    vi.spyOn(api, "work").mockResolvedValue({ slug: "d1", title: "t", version: 1, text: "", state: "ready", job_id: null, notes_ready: true, versions: [1] });
    const start = vi.spyOn(api, "startJob");
    type("稿");
    fireEvent.click(screen.getByRole("button", { name: /交稿並開始分析/ }));
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledWith("d1", true));
    expect(start).not.toHaveBeenCalled();
  });
  it("選檔走 extract 並填入稿子,標題取檔名", async () => {
    mount();
    vi.spyOn(api, "extract").mockResolvedValue({ filename: "海.md", text: "檔案內容", chars: 4 });
    const sub = vi.spyOn(api, "submit").mockResolvedValue({ slug: "d3", title: "海", version: 1, new_version: true, reused: false });
    vi.spyOn(api, "startJob").mockResolvedValue({ job_id: 1 });
    const input = document.querySelector("input[type=file]")!;
    fireEvent.change(input, { target: { files: [new File(["x"], "海.md")] } });
    await waitFor(() => expect((screen.getByRole("textbox", { name: "稿子" }) as HTMLTextAreaElement).value).toBe("檔案內容"));
    fireEvent.click(screen.getByRole("button", { name: /交稿並開始分析/ }));
    await waitFor(() => expect(sub).toHaveBeenCalledWith("檔案內容", "海"));
  });
  it("拖檔進對話框也走 extract", async () => {
    mount();
    const ex = vi.spyOn(api, "extract").mockResolvedValue({ filename: "a.txt", text: "拖來的", chars: 3 });
    fireEvent.drop(screen.getByRole("dialog"), { dataTransfer: { files: [new File(["x"], "a.txt")] } });
    await waitFor(() => expect(ex).toHaveBeenCalled());
    await screen.findByDisplayValue("拖來的");
  });
  it("失敗顯示 den 的錯誤訊息並可再試", async () => {
    mount();
    vi.spyOn(api, "submit").mockRejectedValue(new DashError(422, "story-too-long"));
    type("稿");
    fireEvent.click(screen.getByRole("button", { name: /交稿並開始分析/ }));
    expect((await screen.findByRole("alert")).textContent).toBe("稿子太長了。");
    expect((screen.getByRole("button", { name: /交稿並開始分析/ }) as HTMLButtonElement).disabled).toBe(false);
  });
});
