import { describe, it, expect, vi, beforeEach } from "vitest";
import viz from "./fixtures/viz.json";
import {
  getIndex, getStory, streamCritique, reanalyzeCritique, toIndexFile,
  getRunningCritiques, cancelCritique, getConclusions, getTranscript, extractStory, createStory,
} from "../src/data/client";

type Route = (url: string, init?: RequestInit) => unknown;

/** 假 fetch:依 "METHOD url" 查表;值是函式則呼叫。 */
function routes(map: Record<string, unknown | Route>) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const key = `${init?.method ?? "GET"} ${url}`;
    if (!(key in map)) return { ok: false, status: 404, text: async () => "nf", json: async () => ({}) } as Response;
    const v = map[key];
    const body = typeof v === "function" ? (v as Route)(url, init) : v;
    return { ok: true, status: 200, json: async () => body, text: async () => String(body) } as Response;
  });
  return { fn, calls };
}

function sseResponse(text: string): Response {
  const bytes = new TextEncoder().encode(text);
  let sent = false;
  return {
    ok: true, status: 200,
    body: { getReader: () => ({ read: async () => (sent ? { done: true, value: undefined } : ((sent = true), { done: false, value: bytes })) }) },
  } as unknown as Response;
}

const T = 1_700_000_000;
const entry = (over: any = {}) => ({
  slug: "d01", title: "T", synopsis: "S", nodes: 3, edges: 2,
  current: { analysis: null, feedback: null }, latest_job: null, ...over,
});
const art = (t = T) => ({ id: 1, created_at: t });
const job = (state: string, step: string | null = null, error_class: string | null = null, updated_at = T + 10) =>
  ({ id: 7, state, step, error_class, updated_at });

beforeEach(() => vi.restoreAllMocks());

describe("toIndexFile 翻譯表", () => {
  const one = (e: any) => toIndexFile({ stories: [entry(e)] }).stories[0];

  it("has_viz / has_feedback 看 current", () => {
    const s = one({ current: { analysis: art(), feedback: art() } });
    expect(s.has_viz).toBe(true);
    expect(s.has_feedback).toBe(true);
    expect(one({}).has_viz).toBe(false);
  });
  it("無 job → done/done/false/null", () => {
    const s = one({});
    expect([s.status, s.stage, s.resumable, s.reason]).toEqual(["done", "done", false, null]);
  });
  it("done", () => {
    const s = one({ latest_job: job("done", "criticizer") });
    expect([s.status, s.stage, s.resumable, s.reason]).toEqual(["done", "done", false, null]);
  });
  it("queued / running → running/step??analyst", () => {
    expect(one({ latest_job: job("queued") })).toMatchObject({ status: "running", stage: "analyst", resumable: false, reason: null });
    expect(one({ latest_job: job("running", "criticizer") })).toMatchObject({ status: "running", stage: "criticizer" });
  });
  it("paused → paused/step/true/error_class", () => {
    expect(one({ latest_job: job("paused", "analyst", "usage-limit") }))
      .toMatchObject({ status: "paused", stage: "analyst", resumable: true, reason: "usage-limit" });
  });
  it("failed 但已有 analysis → has_viz && resumable", () => {
    const s = one({ current: { analysis: art(), feedback: null }, latest_job: job("failed", "criticizer", "gate") });
    expect(s).toMatchObject({ has_viz: true, status: "failed", stage: "criticizer", resumable: true, reason: "gate" });
  });
  it("cancelled → failed,reason 缺省 cancelled", () => {
    expect(one({ latest_job: job("cancelled", "analyst") }))
      .toMatchObject({ status: "failed", resumable: true, reason: "cancelled" });
  });
  it("updated = current 與 job 時間取大、ISO", () => {
    const s = one({ current: { analysis: art(T), feedback: null }, latest_job: job("done", null, null, T + 50) });
    expect(s.updated).toBe(new Date((T + 50) * 1000).toISOString());
    const s2 = one({ current: { analysis: art(T + 99), feedback: art(T) } });
    expect(s2.updated).toBe(new Date((T + 99) * 1000).toISOString());
  });
  it("count / 欄位直通", () => {
    const f = toIndexFile({ stories: [entry()] });
    expect(f.count).toBe(1);
    expect(f.stories[0]).toMatchObject({ slug: "d01", title: "T", synopsis: "S", nodes: 3, edges: 2 });
  });
});

describe("dataClient 讀取", () => {
  it("getIndex 打 /api/stories 並翻譯", async () => {
    const { fn } = routes({ "GET /api/stories": { stories: [entry()] } });
    vi.stubGlobal("fetch", fn);
    const r = await getIndex();
    expect(r.stories[0].slug).toBe("d01");
  });
  it("getStory 取 viz + source", async () => {
    const { fn, calls } = routes({
      "GET /api/stories/s02/viz": viz, "GET /api/stories/s02/source": "原文內容",
    });
    vi.stubGlobal("fetch", fn);
    const r = await getStory("s02");
    expect(r.viz.slug).toBe((viz as any).slug);
    expect(r.source).toContain("原文");
    expect(calls.map(c => c.url).sort()).toEqual(["/api/stories/s02/source", "/api/stories/s02/viz"]);
  });
  it("缺檔 throw 可讀錯誤", async () => {
    vi.stubGlobal("fetch", routes({}).fn);
    await expect(getIndex()).rejects.toThrow(/api\/stories/);
  });
  it("結論 / 逐字走 /api/stories/{slug}/...", async () => {
    const { fn } = routes({
      "GET /api/stories/s1/conclusions": { conclusions: [] },
      "GET /api/stories/s1/transcript": { turns: [] },
    });
    vi.stubGlobal("fetch", fn);
    expect((await getConclusions("s1")).conclusions).toEqual([]);
    expect((await getTranscript("s1")).turns).toEqual([]);
  });
  it("extractStory → POST /api/extract", async () => {
    const { fn, calls } = routes({ "POST /api/extract": { filename: "a.txt", text: "x", chars: 1 } });
    vi.stubGlobal("fetch", fn);
    expect((await extractStory(new File(["x"], "a.txt"))).chars).toBe(1);
    expect(calls[0].url).toBe("/api/extract");
  });
  it("createStory → POST /api/stories", async () => {
    const { fn, calls } = routes({ "POST /api/stories": { slug: "d02" } });
    vi.stubGlobal("fetch", fn);
    expect((await createStory("T", "文")).slug).toBe("d02");
    expect(JSON.parse(calls[0].init!.body as string)).toEqual({ title: "T", text: "文" });
  });
});

describe("critique 走 job", () => {
  const frames =
    `data: ${JSON.stringify({ event: "phase", data: { name: "analyst", status: "start", attempt: 1 } })}\n\n` +
    `data: ${JSON.stringify({ event: "done", data: { ok: true } })}\n\n`;

  function critiqueFetch(stream: string = frames) {
    const calls: { url: string; init?: RequestInit }[] = [];
    const fn = vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url === "/api/jobs" && init?.method === "POST")
        return { ok: true, status: 202, json: async () => ({ job_id: 9 }) } as Response;
      if (url === "/api/jobs/9/events") return sseResponse(stream);
      return { ok: false, status: 404 } as Response;
    });
    return { fn, calls };
  }

  it("streamCritique 先 POST /api/jobs 再 GET events,事件原樣(解包)", async () => {
    const { fn, calls } = critiqueFetch();
    vi.stubGlobal("fetch", fn);
    const got: any[] = [];
    for await (const e of streamCritique("d01", "T", true)) got.push(e);
    expect(calls[0].url).toBe("/api/jobs");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(calls[0].init?.body as string)).toEqual({ kind: "critique", slug: "d01" });
    expect(calls[1].url).toBe("/api/jobs/9/events");
    expect(got).toEqual([
      { event: "phase", data: { name: "analyst", status: "start", attempt: 1 } },
      { event: "done", data: { ok: true } },
    ]);
  });
  it("reanalyzeCritique 同構", async () => {
    const { fn, calls } = critiqueFetch();
    vi.stubGlobal("fetch", fn);
    const got: any[] = [];
    for await (const e of reanalyzeCritique("d01", "T")) got.push(e);
    expect(calls.map(c => c.url)).toEqual(["/api/jobs", "/api/jobs/9/events"]);
    expect(got[got.length - 1]).toEqual({ event: "done", data: { ok: true } });
  });
  it("POST /api/jobs 失敗 → throw", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 409 }) as Response));
    await expect((async () => { for await (const _ of streamCritique("d01")) { /* */ } })()).rejects.toThrow(/409/);
  });

  it("running_reattach_then_cancel", async () => {
    const { fn, calls } = routes({
      "GET /api/stories": { stories: [entry({ latest_job: job("running", "criticizer") }), entry({ slug: "d02" })] },
      "POST /api/jobs/7/cancel": {},
    });
    vi.stubGlobal("fetch", fn);
    const running = await getRunningCritiques();
    expect(running).toEqual([{ slug: "d01", title: "T", status: "running", step: 2 }]);
    expect(await cancelCritique("d01")).toBe(true);
    expect(calls[calls.length - 1].url).toBe("/api/jobs/7/cancel");
  });
  it("getRunningCritiques queued 的 step 為 0、status 仍標 running", async () => {
    vi.stubGlobal("fetch", routes({ "GET /api/stories": { stories: [entry({ latest_job: job("queued") })] } }).fn);
    expect((await getRunningCritiques())[0]).toMatchObject({ status: "running", step: 0 });
  });
  it("getRunningCritiques 讀不到 → []", async () => {
    vi.stubGlobal("fetch", routes({}).fn);
    expect(await getRunningCritiques()).toEqual([]);
  });
  it("cancelCritique 沒有進行中的 job → false 且不發 cancel", async () => {
    const { fn, calls } = routes({ "GET /api/stories": { stories: [entry({ latest_job: job("done") })] } });
    vi.stubGlobal("fetch", fn);
    expect(await cancelCritique("d01")).toBe(false);
    expect(await cancelCritique("nope")).toBe(false);
    expect(calls.every(c => c.init?.method !== "POST")).toBe(true);
  });
  it("cancelCritique 打到 cancel 但 den 回 409 → false", async () => {
    const stories = { stories: [entry({ latest_job: job("running", "analyst") })] };
    vi.stubGlobal("fetch", vi.fn(async (url: string) =>
      url === "/api/stories"
        ? ({ ok: true, status: 200, json: async () => stories } as Response)
        : ({ ok: false, status: 409 } as Response)));
    expect(await cancelCritique("d01")).toBe(false);
  });
});

describe("SSE 解析", () => {
  const f = (o: any) => `data: ${JSON.stringify(o)}\n\n`;
  async function run(chunks: string[]) {
    const enc = new TextEncoder();
    let i = 0;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => url === "/api/jobs"
      ? ({ ok: true, json: async () => ({ job_id: 9 }) } as Response)
      : ({ ok: true, body: { getReader: () => ({ read: async () =>
          i < chunks.length ? { done: false, value: enc.encode(chunks[i++]) } : { done: true, value: undefined } }) } } as unknown as Response)));
    const got: any[] = [];
    for await (const e of streamCritique("d01")) got.push(e);
    return got;
  }
  it("frame 被切在 chunk 中間也能拼回", async () => {
    const all = f({ event: "phase", data: { name: "analyst" } }) + f({ event: "done", data: { ok: true } });
    const cut = 17;
    expect(await run([all.slice(0, cut), all.slice(cut, cut + 30), all.slice(cut + 30)])).toEqual([
      { event: "phase", data: { name: "analyst" } }, { event: "done", data: { ok: true } },
    ]);
  });
  it("state:done → done", async () => {
    expect(await run([f({ event: "state", data: { state: "done" } })])).toEqual([{ event: "done", data: { ok: true } }]);
  });
  it.each(["paused", "failed", "cancelled"])("state:%s → error", async (st) => {
    const r = await run([f({ event: "state", data: { state: st, error_class: st === "cancelled" ? null : "gate", detail: { message: "d", resets_at: 1234 } } })]);
    expect(r).toEqual([{ event: "error", data: { reason: st === "cancelled" ? "cancelled" : "gate", message: "d", resets_at: 1234 } }]);
  });
  it("error_class / detail 缺 → cancelled / 空字串", async () => {
    expect(await run([f({ event: "state", data: { state: "failed" } })]))
      .toEqual([{ event: "error", data: { reason: "cancelled", message: "", resets_at: null } }]);
  });
  it("其他 state 原樣穿過", async () => {
    const ev = { event: "state", data: { state: "running" } };
    expect(await run([f(ev)])).toEqual([ev]);
  });
});

describe("getUsage", () => {
  it("仍打 /api/usage/{slug}", async () => {
    const agg = { slug: "s02", empty: false };
    vi.stubGlobal("fetch", routes({ "GET /api/usage/s02": agg }).fn);
    const { getUsage } = await import("../src/data/client");
    expect((await getUsage("s02")).slug).toBe("s02");
  });
});
