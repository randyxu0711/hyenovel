import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import Reader from "../src/dash/Reader";
import { api, type WorkDetail } from "../src/dash/api";
import { setLang } from "../src/dash/i18n";

afterEach(() => vi.restoreAllMocks());
const work = (o: Partial<WorkDetail>): WorkDetail => ({ slug: "d1", title: "海", version: 2, text: "內文", state: "ready", job_id: null, notes_ready: true, ...o });

function mount(w: WorkDetail, onFinished = vi.fn()) {
  setLang("zh-Hant");
  vi.spyOn(api, "work").mockResolvedValue(w);
  render(<Reader slug="d1" companion="鬣狗" onQuote={vi.fn()} onFinished={onFinished} />);
  return onFinished;
}

describe("冷讀者的筆記", () => {
  it("notes_ready=false 且沒在分析:disabled 並說明沒有筆記", async () => {
    mount(work({ notes_ready: false, state: "none" }));
    const b = await screen.findByRole("button", { name: "冷讀者的筆記" }) as HTMLButtonElement;
    expect(b.disabled).toBe(true);
    expect(screen.getByText("還沒有筆記")).toBeTruthy();
  });
  it("分析中:disabled 並說筆記還在寫", async () => {
    vi.spyOn(api, "jobEvents").mockImplementation(async function* () { await new Promise(() => {}); });
    mount(work({ notes_ready: false, state: "notes-running", job_id: 5 }));
    expect((await screen.findByRole("button", { name: "冷讀者的筆記" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("筆記還在寫")).toBeTruthy();
  });
  it("預設不顯示;打開後第一行是冷讀者說明,內文用 markdown,稿仍在", async () => {
    mount(work({}));
    const part = vi.spyOn(api, "part").mockResolvedValue("## 第一點\n\n**粗** 的");
    await screen.findByText("內文");
    expect(part).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "冷讀者的筆記" }));
    const panel = await screen.findByRole("complementary", { name: "冷讀者的筆記" });
    expect(panel.firstElementChild!.textContent).toBe("這是另一位冷讀者的筆記");
    expect(await screen.findByRole("heading", { name: "第一點" })).toBeTruthy();
    expect(screen.getByText("內文")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "收起筆記" }));
    expect(screen.queryByRole("complementary")).toBeNull();
  });
});

describe("分析進度", () => {
  it("顯示步驟;done 後重抓這篇並通知左欄", async () => {
    vi.spyOn(api, "jobEvents").mockImplementation(async function* () {
      yield { event: "phase", data: { name: "analyst", status: "start" } };
      yield { event: "done", data: { ok: true } };
    });
    const onFinished = mount(work({ state: "running", job_id: 5, notes_ready: false }));
    await waitFor(() => expect(onFinished).toHaveBeenCalled());
    await waitFor(() => expect(api.work).toHaveBeenCalledTimes(2));
  });
  it("分析中時滾筒上有記號與「正在讀」", async () => {
    vi.spyOn(api, "jobEvents").mockImplementation(async function* () {
      yield { event: "phase", data: { name: "reviewer", status: "start" } };
      await new Promise(() => {});
    });
    mount(work({ state: "running", job_id: 5 }));
    expect((await screen.findByRole("status")).textContent).toContain("正在讀這一篇");
    await screen.findByText(/寫備課筆記/);
  });
});
