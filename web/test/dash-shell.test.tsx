import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
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
