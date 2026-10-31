import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import Dash from "../src/dash/Dash";
import { setLang } from "../src/dash/i18n";
import { olive, hyena, buffalo, deer } from "./dash-fixtures";

afterEach(() => vi.unstubAllGlobals());
const json = (b: unknown) => new Response(JSON.stringify(b));

function mount(works: object[]) {
  setLang("zh-Hant");
  const f = vi.fn(async (u: string) => {
    if (u === "/api/themes") return json({ themes: [olive], default: "olive" });
    if (u === "/api/characters") return json({ characters: [hyena, buffalo, deer], default: "hyena" });
    if (u === "/api/works") return json({ works });
    if (u.startsWith("/api/works/")) {
      return u.endsWith("/sessions") ? json({ sessions: [] })
        : json({ slug: "d2", title: "最近的", version: 1, text: "內文一行", state: "ready", job_id: null, notes_ready: false });
    }
    return json({ sessions: [] });
  });
  vi.stubGlobal("fetch", f);
  render(<Dash />);
  return f;
}

describe("Dash 起始作品", () => {
  it("沒指定作品時開最近的那篇(清單第一篇)", async () => {
    const f = mount([{ slug: "d2", title: "最近的", version: 1, chars: 4 }, { slug: "d1", title: "舊的", version: 1, chars: 4 }]);
    expect(await screen.findByText("內文一行")).toBeTruthy();
    expect(f.mock.calls.map(c => c[0])).toContain("/api/works/d2");
    expect(f.mock.calls.map(c => c[0])).not.toContain("/api/works/d1");
  });
  it("沒有作品時邀請交第一張稿,中間區留空提示", async () => {
    mount([]);
    expect(await screen.findByText("還沒有作品。捲進第一張稿吧。")).toBeTruthy();
    expect(screen.getByText("選一篇作品,或捲進一張新稿。")).toBeTruthy();
  });
});

describe("Dash 交稿後", () => {
  const draft = async () => {
    fireEvent.click(await screen.findByRole("button", { name: "捲進一張新稿" }));
    fireEvent.change(await screen.findByRole("textbox", { name: "稿子" }), { target: { value: "稿" } });
    fireEvent.click(screen.getByRole("button", { name: /交稿並開始分析/ }));
  };
  const mountSubmitting = () => {
    const f = mount([{ slug: "d2", title: "最近的", version: 1, chars: 4 }]);
    const inner = f.getMockImplementation()!;
    f.mockImplementation(async (u: string, init?: RequestInit) =>
      u === "/api/stories" && init?.method === "POST"
        ? json({ slug: "d2", title: "最近的", version: 1, new_version: false, reused: true })
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
    fireEvent.click(await screen.findByRole("button", { name: /最近的/ }));
    expect(screen.queryByText("這篇已經在了,已切過去。")).toBeNull();
  });
});
