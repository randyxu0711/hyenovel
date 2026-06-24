import { describe, it, expect, vi, beforeEach } from "vitest";
import viz from "./fixtures/viz.json";
import index from "./fixtures/index.json";
import { getIndex, getStory } from "../src/data/client";

function mockFetch(map: Record<string, unknown>) {
  return vi.fn(async (url: string) => {
    if (!(url in map)) return { ok: false, status: 404, text: async () => "nf" } as Response;
    const body = map[url];
    return { ok: true, status: 200,
      json: async () => body, text: async () => String(body) } as Response;
  });
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
});
