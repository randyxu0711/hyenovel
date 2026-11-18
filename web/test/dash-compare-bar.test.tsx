import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation, useSearchParams } from "react-router-dom";
import Reader from "../src/dash/Reader";
import { defaultOld } from "../src/dash/useCompare";
import type { Compare } from "../src/dash/api";
import { setLang } from "../src/dash/i18n";
import { LinksProvider } from "../src/dash/links";
import { CharactersProvider, makeCharacters } from "../src/dash/useCharacters";
import { hyena, buffalo, deer } from "./dash-fixtures";
import { setPaperFlow } from "../src/dash/paperFlow";

beforeEach(() => { setPaperFlow("h"); Element.prototype.scrollIntoView = vi.fn(); });
afterEach(() => vi.unstubAllGlobals());

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
const H = (n: number, noted = true) => ({ n, at: n, analysed: noted, noted });
const detail = (over = {}) => ({
  slug: "d1", title: "海", version: 3, versions: [1, 2, 3], text: "甲。丙。丁。", state: "ready", job_id: null,
  notes_ready: false, history: [H(1), H(2), H(3, false)], ...over,
});
const cmp = (over: Partial<Compare> = {}): Compare => ({
  new: 3, old: 2, mode: "notes", olds: [{ n: 2, noted: true }, { n: 1, noted: true }], same: false, text: "甲。丙。丁。",
  runs: [{ op: "del", id: "d0", at: 2, text: "乙。", chars: 2, pinned: false }, { op: "ins", id: "i0", start: 4, end: 6 }],
  hunks: [{ ids: ["d0"], at: 2 }, { ids: ["i0"], at: 4 }, { ids: ["d0"], at: 2 }], notes_version: 2, points: [], ...over,
});

function Where() { const l = useLocation(); return <output data-testid="loc">{l.search}</output>; }
function Routed({ onCompare }: { onCompare?: (c: Compare | null) => void }) {
  const [search] = useSearchParams();
  const v = Number(search.get("v"));
  return <Reader slug="d1" version={v > 0 ? v : undefined} onQuote={vi.fn()} onCompare={onCompare} />;
}
const mount = async (d: object, c: (u: string) => Response = () => json(cmp()), at = "/w/d1", onCompare?: (c: Compare | null) => void) => {
  setLang("zh-Hant");
  const f = vi.fn(async (u: string) => {
    if (u.includes("/compare")) return c(u);
    const m = /\?v=(\d+)/.exec(u);
    return json(m ? { ...d, version: Number(m[1]) } : d);
  });
  vi.stubGlobal("fetch", f);
  render(
    <MemoryRouter initialEntries={[at]}>
      <CharactersProvider value={makeCharacters([hyena, buffalo, deer], "hyena")}>
        <LinksProvider><Where /><Routed onCompare={onCompare} /></LinksProvider>
      </CharactersProvider>
    </MemoryRouter>);
  await screen.findByRole("heading", { name: "海" });
  return f;
};
const loc = () => screen.getByTestId("loc").textContent ?? "";
const compareCalls = (f: ReturnType<typeof vi.fn>) => f.mock.calls.map(c => c[0] as string).filter(u => u.includes("/compare"));

describe("defaultOld", () => {
  it("newest older noted version, else previous", () => {
    expect(defaultOld([H(1), H(2, false), H(3)], 3)).toBe(1);
    expect(defaultOld([H(1, false), H(2, false)], 2)).toBe(1);
    expect(defaultOld([H(1)], 1)).toBeNull();
  });
});

describe("對照條", () => {
  it("no compare button with one version", async () => {
    await mount(detail({ version: 1, versions: [1], history: [H(1)] }));
    expect(screen.queryByRole("button", { name: /^對照/ })).toBeNull();
  });

  it("compare button opens ?cmp and fetches compare", async () => {
    const seen = vi.fn();
    const f = await mount(detail(), undefined, "/w/d1", seen);
    fireEvent.click(screen.getByRole("button", { name: "對照 v2" }));
    expect(loc()).toBe("?cmp=");
    await screen.findByText("3 處");
    expect(compareCalls(f)).toEqual(["/api/works/d1/compare?v=3"]);
    expect(seen).toHaveBeenLastCalledWith(expect.objectContaining({ old: 2 }));
  });

  it("count shows total then i/n", async () => {
    await mount(detail(), undefined, "/w/d1?cmp");
    await screen.findByText("3 處");
    fireEvent.click(screen.getByRole("button", { name: "下一處" }));
    expect(screen.getByText("1/3")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "上一處" }));
    expect(screen.getByText("3/3")).toBeTruthy();
  });

  it("same shows identical label and no clean button", async () => {
    await mount(detail(), () => json(cmp({ same: true, runs: [], hunks: [] })), "/w/d1?cmp");
    await screen.findByText("與 v2 完全相同");
    expect(screen.queryByRole("button", { name: "僅顯示新版" })).toBeNull();
  });

  it("hides new-version and analyze buttons while comparing", async () => {
    await mount(detail({ state: "none" }), undefined, "/w/d1?cmp");
    await screen.findByText("3 處");
    expect(screen.queryByRole("button", { name: "交新版" })).toBeNull();
    expect(screen.queryByRole("button", { name: "分析這版" })).toBeNull();
  });

  it("old picker lists olds and sets ?cmp=n", async () => {
    const f = await mount(detail(), undefined, "/w/d1?cmp");
    await screen.findByText("3 處");
    fireEvent.click(screen.getByRole("button", { name: "選擇舊版" }));
    fireEvent.click(screen.getByRole("button", { name: /^v1/ }));
    expect(loc()).toBe("?cmp=1");
    await waitFor(() => expect(compareCalls(f)).toContain("/api/works/d1/compare?v=3&from=1"));
  });

  it("clean toggles &clean", async () => {
    await mount(detail(), undefined, "/w/d1?cmp");
    await screen.findByText("3 處");
    fireEvent.click(screen.getByRole("button", { name: "僅顯示新版" }));
    expect(loc()).toBe("?cmp=&clean=");
    fireEvent.click(screen.getByRole("button", { name: "僅顯示新版" }));
    expect(loc()).toBe("?cmp=");
  });

  it("Escape leaves compare (picker first)", async () => {
    await mount(detail(), undefined, "/w/d1?cmp&clean");
    await screen.findByText("3 處");
    fireEvent.click(screen.getByRole("button", { name: "選擇舊版" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(loc()).toBe("?cmp&clean");
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(loc()).toBe("");
  });

  it("close button leaves compare", async () => {
    await mount(detail(), undefined, "/w/d1?cmp");
    await screen.findByText("3 處");
    fireEvent.click(screen.getByRole("button", { name: "結束對照" }));
    expect(loc()).toBe("");
  });

  it("keeps cmp when version changes and falls back from a bad from", async () => {
    const f = await mount(detail(), u => u.includes("from=2")
      ? json({ code: "unknown-version", detail: "x" }, 404) : json(cmp()), "/w/d1?v=3&cmp=2");
    await waitFor(() => expect(compareCalls(f)).toContain("/api/works/d1/compare?v=3"));
    expect(loc()).toBe("?v=3&cmp=");
    await screen.findByText("3 處");
  });

  it("gives up and shows error when default also fails", async () => {
    await mount(detail(), () => json({ code: "unknown-version", detail: "x" }, 404), "/w/d1?cmp");
    await waitFor(() => expect(loc()).toBe(""));
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});
