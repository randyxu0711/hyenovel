import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import Dash from "../src/dash/Dash";
import { setLang } from "../src/dash/i18n";
import { olive, hyena, buffalo, deer } from "./dash-fixtures";

afterEach(() => vi.unstubAllGlobals());
beforeEach(() => localStorage.clear());
const json = (b: unknown) => new Response(JSON.stringify(b));

const WORKS = [
  { slug: "d2", title: "最近的", version: 1, chars: 4, updated_at: 200, state: "ready" },
  { slug: "d1", title: "舊的", version: 1, chars: 4, updated_at: 100, state: "ready" },
];

function Where() { const l = useLocation(); return <output data-testid="loc">{l.pathname}{l.search}</output>; }

function mount(path: string, works: object[] = WORKS) {
  setLang("zh-Hant");
  const f = vi.fn(async (u: string) => {
    if (u === "/api/themes") return json({ themes: [olive], default: "olive" });
    if (u === "/api/characters") return json({ characters: [hyena, buffalo, deer], default: "hyena" });
    if (u === "/api/works") return json({ works });
    if (u.startsWith("/api/works/")) {
      return u.endsWith("/sessions") ? json({ sessions: [] })
        : json({ slug: "d2", title: "最近的", version: 1, versions: [1], text: "內文一行", state: "ready", job_id: null, notes_ready: false });
    }
    return json({ sessions: [] });
  });
  vi.stubGlobal("fetch", f);
  render(<MemoryRouter initialEntries={[path]}>
    <Where />
    <Routes>
      <Route path="/" element={<Dash />} />
      <Route path="/w/:slug" element={<Dash />} />
      <Route path="/settings" element={<Dash />} />
    </Routes>
  </MemoryRouter>);
  return f;
}
const dash = () => document.querySelector(".dash") as HTMLElement;
const nav = () => screen.findByRole("navigation");

describe("Dash 殼與路由", () => {
  it("/ 是 home:左欄展開並列出作品標題,不自動開任何一篇", async () => {
    const f = mount("/");
    const rail = within(await nav());
    expect(await rail.findByText("最近的")).toBeTruthy();
    expect(rail.getByText("舊的")).toBeTruthy();
    expect(dash().dataset.view).toBe("home");
    expect(f.mock.calls.map(c => c[0])).not.toContain("/api/works/d2");
  });
  it("/w/:slug 是 work:左欄收起、沒有作品標題,有作品/設定/切換晝夜三顆鍵", async () => {
    mount("/w/d2");
    expect(await screen.findByText("內文一行")).toBeTruthy();
    const rail = within(await nav());
    expect(dash().dataset.view).toBe("work");
    expect(rail.queryByText("最近的")).toBeNull();
    for (const n of ["作品", "設定", "切換晝夜"]) expect(rail.getByRole("button", { name: n })).toBeTruthy();
  });
  it("?v= 帶進去抓那一版", async () => {
    const f = mount("/w/d2?v=3");
    await screen.findByText("內文一行");
    expect(f.mock.calls.map(c => c[0])).toContain("/api/works/d2?v=3");
  });
  it("/settings 是 settings:左欄收起,有「設定」標題", async () => {
    mount("/settings");
    await nav();
    expect(dash().dataset.view).toBe("settings");
    expect(screen.getByRole("heading", { name: "設定" })).toBeTruthy();
  });
  it("點設定 → /settings;點作品浮層裡的一篇 → /w/<slug>;點新對話 → /", async () => {
    mount("/w/d2");
    const rail = within(await nav());
    fireEvent.click(rail.getByRole("button", { name: "設定" }));
    expect(screen.getByTestId("loc").textContent).toBe("/settings");
    fireEvent.click(rail.getByRole("button", { name: "作品" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /舊的/ }));
    expect(screen.getByTestId("loc").textContent).toBe("/w/d1");
  });
  it("新對話鈕回到 /", async () => {
    mount("/w/d2");
    fireEvent.click(within(await nav()).getByRole("button", { name: "新對話" }));
    expect(screen.getByTestId("loc").textContent).toBe("/");
    expect(dash().dataset.view).toBe("home");
  });
  it("切換晝夜:.dash 的 data-mode 變", async () => {
    mount("/");
    const rail = within(await nav());
    const before = dash().dataset.mode;
    expect(before === "light" || before === "dark").toBe(true);
    fireEvent.click(rail.getByRole("button", { name: "切換晝夜" }));
    expect(dash().dataset.mode).toBe(before === "dark" ? "light" : "dark");
  });
  it("沒有作品時 home 邀請把稿拖進來或貼上", async () => {
    mount("/", []);
    expect((await screen.findByRole("textbox", { name: "對話輸入" }) as HTMLTextAreaElement).placeholder).toBe("把稿拖進來,或貼上");
  });
});

describe("Dash 交稿後", () => {
  const draft = async () => {
    fireEvent.click(within(await nav()).getByRole("button", { name: "作品" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "交一篇新的" }));
    await screen.findByRole("textbox", { name: "對話輸入" });   // 「交一篇新的」回到進門畫面
    fireEvent.drop(document.querySelector(".home")!, { dataTransfer: { files: [new File(["x"], "最近的.md")] } });
    fireEvent.click(await screen.findByRole("button", { name: /交稿並開始分析/ }));
  };
  const mountSubmitting = () => {
    const f = mount("/w/d2");
    const inner = f.getMockImplementation()!;
    f.mockImplementation(async (u: string, init?: RequestInit) =>
      u === "/api/stories" && init?.method === "POST"
        ? json({ slug: "d2", title: "最近的", version: 1, new_version: false, reused: true })
        : u === "/api/extract" ? json({ filename: "最近的.md", text: "稿", chars: 1 })
        : inner(u));
    return f;
  };
  const workFetches = (f: ReturnType<typeof mount>) => f.mock.calls.filter(c => c[0] === "/api/works/d2").length;

  it("重交已開著的那篇:Reader 重抓,並顯示可關掉的提示", async () => {
    const f = mountSubmitting();
    await screen.findByText("內文一行");
    const before = workFetches(f);
    await draft();
    expect(await screen.findByText("這篇已經在了,已切過去。")).toBeTruthy();
    await waitFor(() => expect(workFetches(f)).toBeGreaterThan(before));
    fireEvent.click(screen.getByRole("button", { name: "關閉提示" }));
    expect(screen.queryByText("這篇已經在了,已切過去。")).toBeNull();
  });
  it("提示在下一個動作(選作品)時清掉", async () => {
    mountSubmitting();
    await screen.findByText("內文一行");
    await draft();
    await screen.findByText("這篇已經在了,已切過去。");
    fireEvent.click(within(await nav()).getByRole("button", { name: "作品" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: /最近的/ }));
    expect(screen.queryByText("這篇已經在了,已切過去。")).toBeNull();
  });
});
