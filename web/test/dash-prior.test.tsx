import { describe, it, expect, vi, beforeEach, afterEach, type MockInstance } from "vitest";
import { render, screen, fireEvent, waitFor, act, renderHook } from "@testing-library/react";
import { api, DashError, type Prior as PriorData, type PriorSnapshot } from "../src/dash/api";
import { setLang } from "../src/dash/i18n";
import Prior from "../src/dash/Prior";
import { useTalk } from "../src/dash/useTalk";
import { CharactersProvider, makeCharacters } from "../src/dash/useCharacters";
import { hyena, buffalo, deer } from "./dash-fixtures";

const DAY = 86_400;
const now = Date.now() / 1000;
const data = (over: Partial<PriorData> = {}): PriorData => ({
  enabled: true,
  digests: [
    { id: 11, session: "s-a", at: now - 10 * DAY, text: "結尾的嘻想留著。", edited: false },
    { id: 12, session: "s-b", at: now - 20 * DAY, text: "海豚那段還沒聊完。", edited: false },
  ],
  threads: [
    { id: 21, root_id: 11, text: "湖底的問句是否太直白", quote: "湖底", at: now - 10 * DAY, session: "s-a", stale: false },
    { id: 22, root_id: 12, text: "海豚是體貼或錯過", quote: "海豚", at: now - 20 * DAY, session: "s-b", stale: false },
  ],
  ...over,
});

let prior: MockInstance<typeof api.prior>;
let editDigest: MockInstance<typeof api.editDigest>;
let setEnded: MockInstance<typeof api.setThreadEnded>;
let setTalked: MockInstance<typeof api.setTalked>;

let onGoto: ReturnType<typeof vi.fn<(session: string) => void>>;
const live = (onSkip = vi.fn(), skipped = false) =>
  render(<Prior mode="live" slug="d1" skipped={skipped} onSkip={onSkip} onGoto={onGoto} busy={false} />);
const cut = () => screen.findByRole("button", { name: /^前次對話摘要/ });

beforeEach(() => {
  setLang("zh-Hant"); localStorage.clear(); onGoto = vi.fn();
  prior = vi.spyOn(api, "prior").mockResolvedValue(data());
  editDigest = vi.spyOn(api, "editDigest").mockResolvedValue({ id: 13 });
  setEnded = vi.spyOn(api, "setThreadEnded").mockResolvedValue(undefined);
  setTalked = vi.spyOn(api, "setTalked").mockResolvedValue(undefined);
});
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("Prior live", () => {
  it("renders nothing without digests", async () => {
    prior.mockResolvedValue(data({ digests: [], threads: [] }));
    const r = live();
    await waitFor(() => expect(prior).toHaveBeenCalledWith("d1"));
    await act(async () => {});
    expect(r.container.textContent).toBe("");
  });

  it("renders nothing when the setting is off", async () => {
    prior.mockResolvedValue(data({ enabled: false }));
    const r = live();
    await waitFor(() => expect(prior).toHaveBeenCalled());
    await act(async () => {});
    expect(r.container.textContent).toBe("");
  });

  it("live: count line omits zero threads", async () => {
    prior.mockResolvedValue(data({ threads: [] }));
    live();
    expect((await cut()).textContent).toBe("前次對話摘要 · 2 次");
    expect(screen.queryByText("待續話題")).toBeNull();
  });

  it("live: expanded by default with count, summary and thread links", async () => {
    live();
    const c = await cut();
    expect(c.textContent).toBe("前次對話摘要 · 2 次 · 待續話題 2");
    expect(c.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("結尾的嘻想留著。")).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "前往原對話" })[1]);
    expect(onGoto).toHaveBeenCalledWith("s-b");
    fireEvent.click(screen.getAllByRole("button", { pressed: false }).find(b => b.closest(".chat-prior-days"))!);
    expect(screen.getByText("海豚那段還沒聊完。")).toBeTruthy();
    fireEvent.click(c);
    expect(c.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("海豚那段還沒聊完。")).toBeNull();
  });

  it("edit saves via api and shows new text", async () => {
    live();
    fireEvent.click(await screen.findByRole("button", { name: "編輯" }));
    const box = screen.getByRole("textbox", { name: "摘要" });
    expect((box as HTMLTextAreaElement).value).toBe("結尾的嘻想留著。");
    prior.mockResolvedValue(data({ digests: [{ id: 13, session: "s-a", at: now - 10 * DAY, text: "改過的摘要", edited: true }] }));
    fireEvent.change(box, { target: { value: "改過的摘要" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));
    expect(await screen.findByText("改過的摘要")).toBeTruthy();
    expect(editDigest).toHaveBeenCalledWith(11, "改過的摘要");
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("edit 409 refetches and keeps draft", async () => {
    live();
    fireEvent.click(await screen.findByRole("button", { name: "編輯" }));
    editDigest.mockRejectedValue(new DashError(409, "stale-digest"));
    fireEvent.change(screen.getByRole("textbox", { name: "摘要" }), { target: { value: "我打的字" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(prior).toHaveBeenCalledTimes(2);
    expect((screen.getByRole("textbox", { name: "摘要" }) as HTMLTextAreaElement).value).toBe("我打的字");
  });

  it("skip sends prior:false and shows restore line", async () => {
    const onSkip = vi.fn();
    const r = live(onSkip);
    fireEvent.click(await screen.findByRole("button", { name: "本次不帶入" }));
    expect(onSkip).toHaveBeenCalledWith(true);
    r.rerender(<Prior mode="live" slug="d1" skipped onSkip={onSkip} onGoto={onGoto} busy={false} />);
    expect(screen.getByText("本次對話不帶入前次摘要")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^前次對話摘要/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "恢復帶入" }));
    expect(onSkip).toHaveBeenCalledWith(false);

    const bodies: any[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith("/api/discuss/")) {
        bodies.push(JSON.parse(String(init?.body)));
        return new Response(`data: ${JSON.stringify({ event: "message", data: { role: "assistant", text: "嗯", session_id: "s9", seq: 1, character: "hyena", spans: [] } })}\n\n`);
      }
      return new Response(JSON.stringify({ sessions: [] }));
    }));
    vi.spyOn(api, "session").mockRejectedValue(new DashError(0, "den-down"));
    const chars = makeCharacters([hyena, buffalo, deer], "hyena");
    const h = renderHook(() => useTalk("d1"), { wrapper: ({ children }) => <CharactersProvider value={chars}>{children}</CharactersProvider> });
    act(() => h.result.current.setSkipPrior(true));
    await act(async () => { await h.result.current.send("你好", []); });
    expect(bodies[0].prior).toBe(false);
  });

  it("end toggles thread", async () => {
    live();
    const ring = (await screen.findAllByRole("button", { name: "標為已結束" }))[0];
    fireEvent.click(ring);
    await waitFor(() => expect(setEnded).toHaveBeenCalledWith(21, true));
    const done = await screen.findByRole("button", { name: "取消已結束" });
    expect(done.textContent).toBe("✓");
    expect((await cut()).textContent).toBe("前次對話摘要 · 2 次 · 待續話題 1");
    fireEvent.click(done);
    await waitFor(() => expect(setEnded).toHaveBeenCalledWith(21, false));
    expect(await screen.findAllByRole("button", { name: "標為已結束" })).toHaveLength(2);
  });

  it("goto is an icon button labelled by prior.goto", async () => {
    live();
    await cut();
    const go = screen.getAllByRole("button", { name: "前往原對話" });
    expect(go).toHaveLength(2);
    expect(go[0].textContent).toBe("");
    expect(go[0].getAttribute("title")).toBe("前往原對話");
    expect(go[0].querySelector("svg")).toBeTruthy();
    fireEvent.click(go[0]);
    expect(onGoto).toHaveBeenCalledWith("s-a");
  });

  it("thread dates shown only when threads span sessions", async () => {
    live();
    await cut();
    expect(document.querySelectorAll(".chat-prior-from")).toHaveLength(2);
  });

  it("thread dates hidden when all threads come from one session", async () => {
    prior.mockResolvedValue(data({ threads: [
      { id: 21, root_id: 11, text: "湖底的問句是否太直白", quote: "湖底", at: now - 10 * DAY, session: "s-a", stale: false },
      { id: 22, root_id: 11, text: "海豚是體貼或錯過", quote: "海豚", at: now - 10 * DAY, session: "s-a", stale: false },
    ] }));
    live();
    await cut();
    expect(screen.getByText("湖底的問句是否太直白").querySelector(".chat-prior-from")).toBeNull();
    expect(document.querySelectorAll(".chat-prior-from")).toHaveLength(0);
  });

  it("stale threads hidden", async () => {
    prior.mockResolvedValue(data({ threads: [
      { id: 21, root_id: 11, text: "還在的話題", quote: "湖底", at: now, session: "s-a", stale: false },
      { id: 23, root_id: 11, text: "稿改掉的話題", quote: "舊句", at: now, session: "s-a", stale: true },
    ] }));
    live();
    expect((await cut()).textContent).toBe("前次對話摘要 · 2 次 · 待續話題 1");
    expect(screen.getByText("還在的話題")).toBeTruthy();
    expect(screen.queryByText("稿改掉的話題")).toBeNull();
  });
});

describe("Prior snapshot", () => {
  const snap: PriorSnapshot = {
    digests: [{ id: 11, at: now - 10 * DAY, text: "帶入的那一版" }],
    threads: [
      { id: 21, text: "湖底的問句", quote: "湖底", at: now - 10 * DAY, session: "s-a", ended: false, talked: true },
      { id: 22, text: "海豚那句", quote: "海豚", at: now - 10 * DAY, session: "s-a", ended: true, talked: false },
    ],
  };
  const mount = (s: PriorSnapshot | null = snap) =>
    render(<Prior mode="snapshot" session="s9" snapshot={s} onGoto={onGoto} busy={false} />);

  it("snapshot is read-only and collapsed", async () => {
    mount();
    const c = await cut();
    expect(c.getAttribute("aria-expanded")).toBe("false");
    expect(c.textContent).toBe("前次對話摘要 · 1 次 · 待續話題 1");
    expect(screen.queryByText("帶入的那一版")).toBeNull();
    fireEvent.click(c);
    expect(screen.getByText("帶入的那一版")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "編輯" })).toBeNull();
    expect(screen.queryByRole("button", { name: "本次不帶入" })).toBeNull();
    expect(screen.getByText("本次已討論")).toBeTruthy();
    expect(screen.getByRole("button", { name: "取消已結束" }).textContent).toBe("✓");
    expect(screen.getByRole("button", { name: "標為已結束" }).textContent).toBe("");
    expect(prior).not.toHaveBeenCalled();
  });

  it("talked undo calls api and drops the mark", async () => {
    mount();
    fireEvent.click(await cut());
    fireEvent.click(screen.getByRole("button", { name: "復原" }));
    await waitFor(() => expect(setTalked).toHaveBeenCalledWith("s9", 21, false));
    await waitFor(() => expect(screen.queryByText("本次已討論")).toBeNull());
  });

  it("null snapshot renders nothing", () => {
    const r = mount(null);
    expect(r.container.textContent).toBe("");
  });
});

describe("useTalk prior", () => {
  const chars = makeCharacters([hyena, buffalo, deer], "hyena");
  const hook = () => renderHook(() => useTalk("d1"), { wrapper: ({ children }) => <CharactersProvider value={chars}>{children}</CharactersProvider> });

  it("typing first time calls preparePrior once", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ sessions: [] }))));
    const prep = vi.spyOn(api, "preparePrior").mockResolvedValue(undefined);
    const h = hook();
    act(() => h.result.current.setDraft(""));
    expect(prep).not.toHaveBeenCalled();
    act(() => h.result.current.setDraft("你"));
    act(() => h.result.current.setDraft("你好"));
    expect(prep).toHaveBeenCalledTimes(1);
    expect(prep).toHaveBeenCalledWith("d1");
  });

  it("first turn loads the snapshot; default send has prior:true", async () => {
    const bodies: any[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith("/api/discuss/")) {
        bodies.push(JSON.parse(String(init?.body)));
        return new Response(`data: ${JSON.stringify({ event: "message", data: { role: "assistant", text: "嗯", session_id: "s9", seq: 1, character: "hyena", spans: [] } })}\n\n`);
      }
      return new Response(JSON.stringify({ sessions: [] }));
    }));
    vi.spyOn(api, "preparePrior").mockResolvedValue(undefined);
    const snapshot: PriorSnapshot = { digests: [{ id: 1, at: now, text: "摘" }], threads: [] };
    vi.spyOn(api, "session").mockResolvedValue({ session: "s9", slug: "d1", title: "海", turns: [], legacy: false, version: 1, attachments: [], prior: snapshot });
    const h = hook();
    await act(async () => { await h.result.current.send("你好", []); });
    expect(bodies[0].prior).toBe(true);
    await waitFor(() => expect(h.result.current.prior).toEqual(snapshot));
  });
});

describe("Prior pending memories", () => {
  it("shows pending memories footer while expanded", async () => {
    prior.mockResolvedValue(data({ pending_memories: 2 }));
    const onMemory = vi.fn();
    render(<Prior mode="live" slug="d1" skipped={false} onSkip={vi.fn()} onGoto={onGoto} onMemory={onMemory} busy={false} />);
    await cut();
    expect(screen.getByText("2 條記憶待確認")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "前往記憶" }));
    expect(onMemory).toHaveBeenCalled();
    fireEvent.click(await cut());
    expect(screen.queryByText("2 條記憶待確認")).toBeNull();
  });

  it("hides footer when none pending", async () => {
    prior.mockResolvedValue(data({ pending_memories: 0 }));
    render(<Prior mode="live" slug="d1" skipped={false} onSkip={vi.fn()} onGoto={onGoto} onMemory={vi.fn()} busy={false} />);
    await cut();
    expect(screen.queryByText(/條記憶待確認/)).toBeNull();
  });

  it("hides footer after first message", async () => {
    const s: PriorSnapshot = { digests: data().digests, threads: [] };
    render(<Prior mode="snapshot" session="s9" snapshot={s} onGoto={onGoto} busy={false} />);
    fireEvent.click(await cut());
    expect(screen.queryByText(/條記憶待確認/)).toBeNull();
    expect(screen.queryByRole("button", { name: "前往記憶" })).toBeNull();
  });
});
