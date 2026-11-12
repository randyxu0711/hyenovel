import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useTalk } from "../src/dash/useTalk";
import { setLang } from "../src/dash/i18n";
import { CharactersProvider, makeCharacters } from "../src/dash/useCharacters";
import { hyena, buffalo, deer } from "./dash-fixtures";

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
const sse = (...evs: [string, unknown][]) => new Response(new ReadableStream({
  start(c) {
    const enc = new TextEncoder();
    for (const [event, data] of evs) c.enqueue(enc.encode(`data: ${JSON.stringify({ event, data })}\n\n`));
    c.close();
  },
}));

const turns = () => [
  { seq: 0, role: "user", text: "問", ts: 1, character: null, quotes: [], spans: [] },
  { seq: 1, role: "assistant", text: "舊的", ts: 2, character: "hyena", quotes: [], spans: [],
    reaction: { mark: "misread", comment: null }, voice: true, edited: false, variant: { n: 1, total: 1 } },
];
let redo: () => Response;
let detail: () => object;
let puts: { url: string; body: unknown }[];

beforeEach(() => {
  setLang("zh-Hant"); localStorage.clear(); puts = [];
  detail = () => ({ session: "s1", slug: null, title: null, turns: turns(), legacy: false, version: null, attachments: [] });
  redo = () => sse(["token", { text: "新" }], ["token", { text: "的" }],
    ["message", { role: "assistant", text: "新的", session_id: "s1", seq: 1, character: "hyena", spans: [], v: null, attachment: null, variant: 2, variants: 2 }],
    ["done", { ok: true, session_id: "s1" }]);
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/characters") return json({ characters: [hyena, buffalo, deer], default: "hyena" });
    if (url.endsWith("/regenerate")) return redo();
    if (init?.method === "PUT") { puts.push({ url, body: init.body ? JSON.parse(String(init.body)) : null }); return json({ variant: 1, variants: 2, edited: true }); }
    if (url.startsWith("/api/sessions/s1")) return json(detail());
    return json({});
  }));
});
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const opened = async () => {
  const chars = makeCharacters([hyena, buffalo, deer], "hyena");
  const h = renderHook(() => useTalk(null, undefined, null, "s1"),
    { wrapper: ({ children }) => <CharactersProvider value={chars}>{children}</CharactersProvider> });
  await waitFor(() => expect(h.result.current.turns).toHaveLength(2));
  return h;
};

describe("重說", () => {
  it("成功:同一格換字、列數不變、新版號、記號清空", async () => {
    const h = await opened();
    let ok = false;
    await act(async () => { ok = await h.result.current.regenerate(1); });
    expect(ok).toBe(true);
    const t = h.result.current.turns;
    expect(t).toHaveLength(2);
    expect(t[1]).toMatchObject({ seq: 1, text: "新的", variant: { n: 2, total: 2 }, reaction: null, voice: false });
    expect(h.result.current.redoing).toBeNull();
    expect(h.result.current.streaming).toBeNull();
  });

  it("失敗:那格回到舊字、有錯誤", async () => {
    redo = () => sse(["token", { text: "半" }], ["error", { code: "chat-failed", message: "x" }]);
    const h = await opened();
    let ok = true;
    await act(async () => { ok = await h.result.current.regenerate(1); });
    expect(ok).toBe(false);
    expect(h.result.current.turns[1]).toMatchObject({ text: "舊的", variant: { n: 1, total: 1 } });
    expect(h.result.current.error?.code).toBe("chat-failed");
    expect(h.result.current.redoing).toBeNull();
  });

  it("重說進行中 redoing 指著那格,串流的字不另開一則", async () => {
    let release!: () => void;
    redo = () => new Response(new ReadableStream({
      start(c) {
        c.enqueue(new TextEncoder().encode(`data: ${JSON.stringify({ event: "token", data: { text: "新" } })}\n\n`));
        release = () => c.close();
      },
    }));
    const h = await opened();
    let p!: Promise<boolean>;
    act(() => { p = h.result.current.regenerate(1); });
    await waitFor(() => expect(h.result.current.streaming).toBe("新"));
    expect(h.result.current.redoing).toBe(1);
    expect(h.result.current.turns).toHaveLength(2);
    await act(async () => { release(); await p; });
  });
});

describe("挑版、改字", () => {
  it("挑版送 n 後重抓", async () => {
    const h = await opened();
    detail = () => ({ session: "s1", slug: null, title: null, legacy: false, version: null, attachments: [],
      turns: [turns()[0], { ...turns()[1], text: "另一版", variant: { n: 2, total: 2 } }] });
    await act(async () => { await h.result.current.pickVariant(1, 2); });
    expect(puts).toEqual([{ url: "/api/sessions/s1/turns/1/variant", body: { n: 2 } }]);
    await waitFor(() => expect(h.result.current.turns[1].text).toBe("另一版"));
  });

  it("改字送全文後重抓", async () => {
    const h = await opened();
    detail = () => ({ session: "s1", slug: null, title: null, legacy: false, version: null, attachments: [],
      turns: [turns()[0], { ...turns()[1], text: "我改的", edited: true }] });
    await act(async () => { await h.result.current.editReply(1, "我改的"); });
    expect(puts).toEqual([{ url: "/api/sessions/s1/turns/1/text", body: { text: "我改的" } }]);
    await waitFor(() => expect(h.result.current.turns[1]).toMatchObject({ text: "我改的", edited: true }));
  });

  it("markVoice 只動目前這局那一則", async () => {
    const h = await opened();
    act(() => { h.result.current.markVoice("other", 1, false); });
    expect(h.result.current.turns[1].voice).toBe(true);
    act(() => { h.result.current.markVoice("s1", 1, false); });
    expect(h.result.current.turns[1].voice).toBe(false);
  });
});
