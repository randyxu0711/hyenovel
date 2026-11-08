import { describe, it, expect, vi, beforeEach, afterEach, type MockInstance } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { api, DashError } from "../src/dash/api";
import { setLang } from "../src/dash/i18n";
import Reaction from "../src/dash/Reaction";

const STOP = "讓我停下來想", MISREAD = "讀錯了";
const mount = (initial: { mark: "stopped" | "misread"; comment: string | null } | null = null) => {
  const r = render(<Reaction session="sid" seq={3} initial={initial} onChange={changed} />);
  fireEvent.click(screen.getByRole("button", { expanded: false }));
  return r;
};
const flush = () => new Promise(r => setTimeout(r));
const pressed = (name: string) => screen.getByRole("button", { name }).getAttribute("aria-pressed");

let changed: ReturnType<typeof vi.fn>;
let set: MockInstance<typeof api.setReaction>;
let clear: MockInstance<typeof api.clearReaction>;

beforeEach(() => {
  setLang("zh-Hant");
  changed = vi.fn();
  set = vi.spyOn(api, "setReaction").mockResolvedValue({ mark: "stopped", comment: null });
  clear = vi.spyOn(api, "clearReaction").mockResolvedValue(undefined);
});
afterEach(() => vi.restoreAllMocks());

describe("Reaction", () => {
  it("按記號送出,再按一次取消", async () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: STOP }));
    expect(pressed(STOP)).toBe("true");
    await waitFor(() => expect(set).toHaveBeenCalledWith("sid", 3, "stopped", undefined));
    fireEvent.click(screen.getByRole("button", { name: STOP }));
    expect(pressed(STOP)).toBe("false");
    await waitFor(() => expect(clear).toHaveBeenCalledWith("sid", 3));
    expect(changed.mock.calls.map(c => c[0]?.mark ?? null)).toEqual(["stopped", null]);
  });

  it("按另一個就替換,短評不沿用", async () => {
    mount({ mark: "stopped", comment: "舊短評" });
    fireEvent.click(screen.getByRole("button", { name: MISREAD }));
    expect(pressed(STOP)).toBe("false");
    expect(pressed(MISREAD)).toBe("true");
    await waitFor(() => expect(set).toHaveBeenCalledWith("sid", 3, "misread", undefined));
    expect((screen.getByRole("textbox", { name: "補一句" }) as HTMLInputElement).value).toBe("");
  });

  it("沒選記號時沒有短評框", () => {
    mount();
    expect(screen.queryByRole("textbox", { name: "補一句" })).toBeNull();
  });

  it("Enter 送出短評;注音選字中的 Enter 不送", async () => {
    mount({ mark: "misread", comment: null });
    const box = screen.getByRole("textbox", { name: "補一句" });
    fireEvent.change(box, { target: { value: "不是這樣" } });
    fireEvent.keyDown(box, { key: "Enter", isComposing: true });
    await flush();
    expect(set).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Enter" });
    await waitFor(() => expect(set).toHaveBeenCalledWith("sid", 3, "misread", "不是這樣"));
  });

  it("失焦送出;內容沒變不重送", async () => {
    mount({ mark: "misread", comment: "同一句" });
    const box = screen.getByRole("textbox", { name: "補一句" });
    fireEvent.blur(box);
    await flush();
    expect(set).not.toHaveBeenCalled();
    fireEvent.change(box, { target: { value: "另一句" } });
    fireEvent.blur(box);
    fireEvent.blur(box);
    await flush();
    expect(set).toHaveBeenCalledTimes(1);
  });

  it("送出失敗:記號退回並顯示錯誤,也通知外層", async () => {
    set.mockRejectedValueOnce(new DashError(422, "bad-mark"));
    mount();
    fireEvent.click(screen.getByRole("button", { name: MISREAD }));
    await waitFor(() => expect(pressed(MISREAD)).toBe("false"));
    expect(screen.getByRole("alert").textContent).toBe("沒有這種記號。");
    expect(changed).toHaveBeenLastCalledWith(null);
  });

  it("連續失敗退回最後存成功的狀態,不是樂觀狀態", async () => {
    set.mockRejectedValue(new DashError(0, "den-down"));
    mount();
    fireEvent.click(screen.getByRole("button", { name: STOP }));
    fireEvent.click(screen.getByRole("button", { name: MISREAD }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(pressed(STOP)).toBe("false");
    expect(pressed(MISREAD)).toBe("false");
  });

  it("請求依點擊順序一個一個送", async () => {
    let finish!: () => void;
    set.mockImplementationOnce(() => new Promise(r => { finish = () => r({ mark: "stopped", comment: null }); }));
    mount();
    fireEvent.click(screen.getByRole("button", { name: STOP }));
    await waitFor(() => expect(set).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: STOP }));
    await flush();
    expect(clear).not.toHaveBeenCalled();
    finish();
    await waitFor(() => expect(clear).toHaveBeenCalledTimes(1));
  });

  it("前一個請求失敗不影響後面的選擇", async () => {
    set.mockRejectedValueOnce(new DashError(0, "den-down"));
    mount();
    fireEvent.click(screen.getByRole("button", { name: STOP }));
    fireEvent.click(screen.getByRole("button", { name: MISREAD }));
    await waitFor(() => expect(set).toHaveBeenLastCalledWith("sid", 3, "misread", undefined));
    expect(pressed(MISREAD)).toBe("true");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("Reaction 標記鈕", () => {
  const bare = (initial: { mark: "stopped" | "misread"; comment: string | null } | null = null) =>
    render(<Reaction session="sid" seq={3} initial={initial} onChange={changed} />);

  it("沒標過:只有一顆「標記這則」,選項收著", () => {
    bare();
    expect(screen.getByRole("button", { name: "標記這則" }).getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("button", { name: STOP })).toBeNull();
  });

  it("打開後選項露字,並說明這局不會變", () => {
    bare();
    fireEvent.click(screen.getByRole("button", { name: "標記這則" }));
    expect(screen.getByRole("button", { name: STOP }).textContent).toBe(STOP);
    expect(screen.getByRole("button", { name: MISREAD }).textContent).toBe(MISREAD);
    expect(screen.getByText("只留著之後調讀伴用,這局不會變。")).toBeTruthy();
  });

  it("標過的回覆露出記號膠囊,點它重開選單", () => {
    bare({ mark: "stopped", comment: null });
    const pill = screen.getByRole("button", { name: "標記:停下來想" });
    expect(pill.textContent).toBe("停下來想");
    fireEvent.click(pill);
    expect(pressed(STOP)).toBe("true");
  });

  it("Esc 關選單、焦點回到標記鈕", () => {
    bare();
    const key = screen.getByRole("button", { name: "標記這則" });
    fireEvent.click(key);
    fireEvent.keyDown(screen.getByRole("button", { name: STOP }), { key: "Escape" });
    expect(screen.queryByRole("button", { name: STOP })).toBeNull();
    expect(document.activeElement).toBe(key);
  });

  it("點選單外面關選單,寫到一半的補充照存", async () => {
    bare({ mark: "misread", comment: null });
    fireEvent.click(screen.getByRole("button", { name: "標記:讀錯了" }));
    const box = screen.getByRole("textbox", { name: "補一句" });
    box.focus();
    fireEvent.change(box, { target: { value: "不是這樣" } });
    fireEvent.mouseDown(document.body);
    await waitFor(() => expect(set).toHaveBeenCalledWith("sid", 3, "misread", "不是這樣"));
    expect(screen.queryByRole("textbox", { name: "補一句" })).toBeNull();
  });
});

describe("api", () => {
  it("clearReaction 接受 204 空回應", async () => {
    vi.restoreAllMocks();
    const f = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", f);
    await expect(api.clearReaction("a b", 3)).resolves.toBeUndefined();
    expect(f.mock.calls[0]).toEqual(["/api/sessions/a%20b/turns/3/reaction", { method: "DELETE" }]);
    vi.unstubAllGlobals();
  });
});
