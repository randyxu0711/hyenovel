import { describe, it, expect, vi, afterEach } from "vitest";
import { api, DashError } from "../src/dash/api";

afterEach(() => vi.unstubAllGlobals());

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("dash api", () => {
  it("網路失敗變成 den-down", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    await expect(api.characters()).rejects.toMatchObject({ code: "den-down", status: 0 });
  });
  it("錯誤回應丟 DashError { status, code, params }", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "x", code: "unknown-work", params: { slug: "d9" } }, 404)));
    const e = await api.work("d9").catch(x => x);
    expect(e).toBeInstanceOf(DashError);
    expect(e).toMatchObject({ status: 404, code: "unknown-work", params: { slug: "d9" } });
  });
  it("沒有 code 或不是 JSON 的錯誤 → unknown", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("boom", { status: 500 })));
    await expect(api.works()).rejects.toMatchObject({ status: 500, code: "unknown" });
  });
  it("只打 /api/*,並正確編碼", async () => {
    const f = vi.fn(async (_u: string) => json({ works: [], sessions: [], estimate: null }));
    vi.stubGlobal("fetch", f);
    await api.works(); await api.sessions("d01"); await api.recentSessions(5); await api.estimate(100);
    expect(f.mock.calls.map(c => c[0])).toEqual([
      "/api/works", "/api/works/d01/sessions", "/api/sessions?limit=5", "/api/estimate?chars=100"]);
  });
  it("talk 送 POST 並解析 SSE;網路斷 → den-down", async () => {
    const body = new ReadableStream({ start(c) {
      c.enqueue(new TextEncoder().encode('data: {"event":"token","data":{"t":"嗨"}}\n\n')); c.close(); } });
    const f = vi.fn(async (_u: string, _i?: RequestInit) => new Response(body, { status: 200 }));
    vi.stubGlobal("fetch", f);
    const evs = [];
    for await (const ev of api.talk("d01", { session: null, message: "hi", character: "hyena", quotes: ["q"] })) evs.push(ev);
    expect(evs).toEqual([{ event: "token", data: { t: "嗨" } }]);
    const [url, init] = f.mock.calls[0];
    expect(url).toBe("/api/discuss/d01");
    expect(JSON.parse(init!.body as string)).toEqual({ session_id: null, message: "hi", character: "hyena", quotes: ["q"] });

    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("x"); }));
    await expect((async () => { for await (const _ of api.jobEvents(3)); })()).rejects.toMatchObject({ code: "den-down" });
  });
  it("startJob 打 critique job", async () => {
    const f = vi.fn(async (_u: string, _i?: RequestInit) => json({ job_id: 7 }, 202));
    vi.stubGlobal("fetch", f);
    expect(await api.startJob("d01")).toEqual({ job_id: 7 });
    expect(JSON.parse(f.mock.calls[0][1]!.body as string)).toEqual({ kind: "critique", slug: "d01" });
  });
});
