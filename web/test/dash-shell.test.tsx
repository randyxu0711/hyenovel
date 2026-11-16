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
  it("/ 是 home:書架展開時列出作品標題,不自動開任何一篇", async () => {
    localStorage.setItem("hyenovel.shelf", "open");
    const f = mount("/");
    const rail = within(await nav());
    expect(await rail.findByText("最近的")).toBeTruthy();
    expect(rail.getByText("舊的")).toBeTruthy();
    expect(dash().dataset.view).toBe("home");
    expect(f.mock.calls.map(c => c[0])).not.toContain("/api/works/d2");
  });
  it("/w/:slug 是 work;窄條沒有作品標題,有找作品/設定鍵", async () => {
    localStorage.setItem("hyenovel.shelf", "rail");
    mount("/w/d2");
    expect(await screen.findByText("內文一行")).toBeTruthy();
    const rail = within(await nav());
    expect(dash().dataset.view).toBe("work");
    expect(rail.queryByText("舊的")).toBeNull();
    for (const n of ["找作品", "設定"]) expect(rail.getByRole("button", { name: n })).toBeTruthy();
  });
  it("?v= 帶進去抓那一版", async () => {
    const f = mount("/w/d2?v=3");
    await screen.findByText("內文一行");
    expect(f.mock.calls.map(c => c[0])).toContain("/api/works/d2?v=3");
  });
  it("/settings 是 settings:設定區開在外觀", async () => {
    mount("/settings");
    await nav();
    expect(dash().dataset.view).toBe("settings");
    expect(screen.getByRole("region", { name: "設定" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1, name: "外觀" })).toBeTruthy();
  });
  it("點設定 → /settings;回去鍵回到那篇;點書架的一篇 → /w/<slug>;書架形態不隨畫面改變", async () => {
    localStorage.setItem("hyenovel.shelf", "open");
    mount("/w/d2");
    const rail = within(await nav());
    fireEvent.click(await rail.findByRole("button", { name: "設定" }));
    expect(screen.getByTestId("loc").textContent).toBe("/settings");
    expect(dash().dataset.shelf).toBe("open");
    fireEvent.click(await rail.findByRole("button", { name: "返回" }));
    expect(screen.getByTestId("loc").textContent).toBe("/w/d2");
    fireEvent.click(await rail.findByRole("button", { name: /^舊的/ }));
    expect(screen.getByTestId("loc").textContent).toBe("/w/d1");
    expect(dash().dataset.shelf).toBe("open");
  });
  it("⌘\\ 與 Ctrl+\\ 切換書架展開/窄條", async () => {
    localStorage.setItem("hyenovel.shelf", "open");
    mount("/");
    await nav();
    expect(dash().dataset.shelf).toBe("open");
    fireEvent.keyDown(document, { key: "\\", metaKey: true });
    expect(dash().dataset.shelf).toBe("rail");
    fireEvent.keyDown(document, { key: "\\", ctrlKey: true });
    expect(dash().dataset.shelf).toBe("open");
    expect(localStorage.getItem("hyenovel.shelf")).toBe("open");
  });
  it("交新稿鈕回到 /", async () => {
    mount("/w/d2");
    fireEvent.click(within(await nav()).getByRole("button", { name: "開一局聊天" }));
    expect(screen.getByTestId("loc").textContent).toBe("/");
    expect(dash().dataset.view).toBe("home");
  });
  it("⌘K 切換晝夜:.dash 的 data-mode 變", async () => {
    mount("/");
    await nav();
    const before = dash().dataset.mode;
    expect(before === "light" || before === "dark").toBe(true);
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    fireEvent.click(await screen.findByRole("option", { name: "切換晝夜" }));
    expect(dash().dataset.mode).toBe(before === "dark" ? "light" : "dark");
  });
  it("沒有作品時 home 邀請把稿拖進來", async () => {
    mount("/", []);
    const box = await screen.findByRole("textbox", { name: "對話輸入" });
    await waitFor(() => expect((box as HTMLTextAreaElement).placeholder).toMatch(/貼上一篇稿/));
  });
});
