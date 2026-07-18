import { describe, it, expect, vi, beforeEach } from "vitest";
import viz from "./fixtures/viz.json";
import index from "./fixtures/index.json";
import { getIndex, getStory, streamCritique, reanalyzeCritique } from "../src/data/client";

function mockFetch(map: Record<string, unknown>) {
  return vi.fn(async (url: string) => {
    if (!(url in map)) return { ok: false, status: 404, text: async () => "nf" } as Response;
    const body = map[url];
    return { ok: true, status: 200,
      json: async () => body, text: async () => String(body) } as Response;
  });
}

/** 假 fetch:回一個讀一次就 done 的 ReadableStream(SSE reader 不會卡住),並記錄每次呼叫的 url/init。 */
function mockStreamFetch() {
  const calls: { url: string; init?: RequestInit }[] = [];
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    return {
      ok: true, status: 200,
      body: { getReader: () => ({ read: async () => ({ done: true, value: undefined }) }) },
    } as unknown as Response;
  });
  return { fn, calls };
}

beforeEach(() => vi.restoreAllMocks());

describe("dataClient", () => {
  it("getIndex 解析 index.json", async () => {
    vi.stubGlobal("fetch", mockFetch({ "/data/index.json": index }));
    const r = await getIndex();
    expect(r.stories.length).toBe((index as any).count);
  });
  it("getStory 取 viz + source", async () => {
    vi.stubGlobal("fetch", mockFetch({
      "/data/s02/viz.json": viz, "/data/s02/source.md": "原文內容",
    }));
    const r = await getStory("s02");
    expect(r.viz.slug).toBe((viz as any).slug);
    expect(r.source).toContain("原文");
  });
  it("缺檔 throw 可讀錯誤", async () => {
    vi.stubGlobal("fetch", mockFetch({}));
    await expect(getIndex()).rejects.toThrow(/index\.json/);
  });
  it("getUsage 打 /api/usage/{slug} 並解析", async () => {
    const agg = { slug: "s02", empty: false, phases: {}, total: {}, cache_read_ratio: 0, retry_cost_usd: 0, retry_count: 0 };
    vi.stubGlobal("fetch", mockFetch({ "/api/usage/s02": agg }));
    const { getUsage } = await import("../src/data/client");
    const r = await getUsage("s02");
    expect(r.slug).toBe("s02");
  });
  it("reanalyzeCritique 打 /api/critique/{slug},body 含 mode:reanalyze", async () => {
    const { fn, calls } = mockStreamFetch();
    vi.stubGlobal("fetch", fn);
    for await (const _ of reanalyzeCritique("s01", "T")) { /* drain */ }
    expect(calls.length).toBe(1);
    expect(calls[0].url).toBe("/api/critique/s01");
    expect(calls[0].init?.method).toBe("POST");
    const body = JSON.parse(calls[0].init?.body as string);
    expect(body.mode).toBe("reanalyze");
  });
  it("streamCritique(resume/normal) body 不含 mode", async () => {
    const { fn, calls } = mockStreamFetch();
    vi.stubGlobal("fetch", fn);
    for await (const _ of streamCritique("s01", "T", false)) { /* drain */ }
    expect(calls.length).toBe(1);
    expect(calls[0].url).toBe("/api/critique/s01");
    const body = JSON.parse(calls[0].init?.body as string);
    expect("mode" in body).toBe(false);
    expect(body.mode).toBeUndefined();
  });
});
