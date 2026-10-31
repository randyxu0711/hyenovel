import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import Rail from "../src/dash/Rail";
import { setLang } from "../src/dash/i18n";
import { CharactersProvider, makeCharacters } from "../src/dash/useCharacters";
import { hyena, buffalo, deer } from "./dash-fixtures";

afterEach(() => vi.unstubAllGlobals());
const json = (b: unknown) => new Response(JSON.stringify(b));
const sess = (n: number, extra = {}) => ({ session: `s${n}`, started_at: n, last_at: n, turns: 2, character: "hyena", mode: "slow", preview: `預覽${n}`, version: 1, ...extra });

function mount(current: string | null, mine = 5) {
  setLang("zh-Hant");
  vi.stubGlobal("fetch", vi.fn(async (u: string) => {
    if (u === "/api/works") return json({ works: [
      { slug: "d1", title: "海", state: "ready", version: 3, chars: 1200 }, { slug: "d2", title: "山", state: "running", version: 1, chars: 50 }, { slug: "d3", title: "湖", state: "none" }] });
    if (u === "/api/works/d1/sessions") return json({ sessions: Array.from({ length: mine }, (_, i) => sess(i + 1)) });
    if (u.startsWith("/api/sessions")) return json({ sessions: [{ ...sess(9, { character: "gone", mode: "direct" }), slug: "d2", title: "山" }] });
    throw new Error(u);
  }));
  const onPick = vi.fn(), onPickSession = vi.fn();
  render(<CharactersProvider value={makeCharacters([hyena, buffalo, deer], "hyena")}>
    <Rail current={current} onPick={onPick} onPickSession={onPickSession} /></CharactersProvider>);
  return { onPick, onPickSession };
}

describe("Rail", () => {
  it("列出作品並標出分析中", async () => {
    const { onPick } = mount(null);
    const works = within(await screen.findByRole("region", { name: "作品" }));
    await works.findByText("海");
    const mountain = works.getByText("山").closest("button")!;
    expect(mountain.textContent).toContain("正在讀");
    expect(works.getByText("海").closest("button")!.textContent).not.toContain("正在讀");
    fireEvent.click(mountain);
    expect(onPick).toHaveBeenCalledWith("d2");
  });
  it("每篇都顯示版本與字數;缺欄位就不顯示", async () => {
    mount(null);
    const works = within(await screen.findByRole("region", { name: "作品" }));
    await works.findByText("海");
    expect(works.getByText("第 3 版 · 1200 字")).toBeTruthy();
    expect(works.getByText("湖").closest("button")!.textContent).toBe("湖");
  });
  it("切換作品時,前一篇的局不會留在新作品底下", async () => {
    let release!: () => void;
    const gate = new Promise<void>(r => { release = r; });
    setLang("zh-Hant");
    vi.stubGlobal("fetch", vi.fn(async (u: string) => {
      if (u === "/api/works") return json({ works: [{ slug: "d1", title: "海" }, { slug: "d2", title: "山" }] });
      if (u === "/api/works/d1/sessions") return json({ sessions: [sess(1)] });
      if (u === "/api/works/d2/sessions") { await gate; return json({ sessions: [sess(7)] }); }
      return json({ sessions: [] });
    }));
    const chars = makeCharacters([hyena], "hyena");
    const el = (c: string) => <CharactersProvider value={chars}><Rail current={c} onPick={vi.fn()} onPickSession={vi.fn()} /></CharactersProvider>;
    const { rerender } = render(el("d1"));
    await screen.findAllByText("預覽1");
    rerender(el("d2"));
    await screen.findByText("山");
    expect(screen.queryByText("預覽1")).toBeNull();
    release();
    expect(await screen.findByText("預覽7")).toBeTruthy();
  });
  it("沒有作品時邀請交第一張稿", async () => {
    setLang("zh-Hant");
    vi.stubGlobal("fetch", vi.fn(async (u: string) => json(u === "/api/works" ? { works: [] } : { sessions: [] })));
    render(<CharactersProvider value={makeCharacters([hyena], "hyena")}><Rail current={null} onPick={vi.fn()} onPickSession={vi.fn()} /></CharactersProvider>);
    expect(await screen.findByText("還沒有作品。捲進第一張稿吧。")).toBeTruthy();
  });
  it("只列最近 3 局加全部", async () => {
    const { onPickSession } = mount("d1");
    const works = within(await screen.findByRole("region", { name: "作品" }));
    await works.findByText("預覽3");
    expect(works.queryByText("預覽4")).toBeNull();
    fireEvent.click(works.getByText("預覽2"));
    expect(onPickSession).toHaveBeenCalledWith("d1", "s2");
    fireEvent.click(works.getByRole("button", { name: "全部" }));
    expect(works.getByText("預覽5")).toBeTruthy();
    expect(works.queryByRole("button", { name: "全部" })).toBeNull();
  });
  it("3 局以內不出現全部", async () => {
    mount("d1", 2);
    const works = within(await screen.findByRole("region", { name: "作品" }));
    await works.findByText("預覽2");
    expect(works.queryByRole("button", { name: "全部" })).toBeNull();
  });
  it("對話區列最近的局,頭像取自角色資料(找不到角色退同 mode)", async () => {
    const { onPickSession } = mount(null);
    const convos = within(await screen.findByRole("region", { name: "對話" }));
    const row = (await convos.findByText("預覽9")).closest("button")!;
    expect(row.textContent).toContain("山");
    expect(row.querySelector("svg, .avatar-fallback")).toBeTruthy();
    fireEvent.click(row);
    expect(onPickSession).toHaveBeenCalledWith("d2", "s9");
  });
});

describe("Rail refresh", () => {
  it("refresh 一變就重抓作品清單,不先清空", async () => {
    setLang("zh-Hant");
    let n = 0;
    vi.stubGlobal("fetch", vi.fn(async (u: string) => {
      if (u === "/api/works") return json({ works: [{ slug: "d1", title: n++ ? "新標題" : "海" }] });
      return json({ sessions: [] });
    }));
    const chars = makeCharacters([hyena], "hyena");
    const el = (r: number) => <CharactersProvider value={chars}><Rail current={null} refresh={r} onPick={vi.fn()} onPickSession={vi.fn()} /></CharactersProvider>;
    const { rerender } = render(el(0));
    await screen.findByText("海");
    rerender(el(1));
    expect(screen.getByText("海")).toBeTruthy();
    await screen.findByText("新標題");
  });
});
