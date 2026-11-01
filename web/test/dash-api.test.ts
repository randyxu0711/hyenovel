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
  it("版本與 legacy 查詢參數", async () => {
    const f = vi.fn(async (_u: string) => json({ sessions: [] }));
    vi.stubGlobal("fetch", f);
    await api.work("d1", 2); await api.map("d1"); await api.map("d1", 3); await api.session("s1", 2);
    await api.sessions("d1", { legacy: true }); await api.recentSessions(5, { legacy: true });
    expect(f.mock.calls.map(c => c[0])).toEqual([
      "/api/works/d1?v=2", "/api/works/d1/map", "/api/works/d1/map?v=3", "/api/sessions/s1?v=2",
      "/api/works/d1/sessions?legacy=1", "/api/sessions?limit=5&legacy=1"]);
  });
  it("startJob 打 critique job", async () => {
    const f = vi.fn(async (_u: string, _i?: RequestInit) => json({ job_id: 7 }, 202));
    vi.stubGlobal("fetch", f);
    expect(await api.startJob("d01")).toEqual({ job_id: 7 });
    expect(JSON.parse(f.mock.calls[0][1]!.body as string)).toEqual({ kind: "critique", slug: "d01" });
  });
  it("串流的非 2xx 保留 den 的 code(talk 與 jobEvents)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "這一局還有一輪在跑", code: "busy", params: {} }, 409)));
    const drain = async (g: AsyncGenerator<unknown>) => { for await (const _ of g); };
    await expect(drain(api.talk("d01", { session: "s", message: "x", character: "hyena", quotes: [] })))
      .rejects.toMatchObject({ status: 409, code: "busy" });
    await expect(drain(api.jobEvents(3))).rejects.toMatchObject({ status: 409, code: "busy" });
  });
  it("submit 回 den 的完整形狀(含 reused)", async () => {
    const r = { slug: "d01", title: "t", version: 2, new_version: false, reused: true };
    vi.stubGlobal("fetch", vi.fn(async () => json(r, 201)));
    expect((await api.submit("文")).reused).toBe(true);
  });
});
