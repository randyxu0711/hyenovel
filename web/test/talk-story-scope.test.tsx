/* 討論的作用域是「篇」,不是「當下選中的節點」。

   資料層早就這樣決定了:後端 `Session.slug`、`transcript.jsonl`、`conclusions.jsonl`、
   `recall(slug, anchors=...)` 全是 by story,node 只是 `anchors`/`refs` 標註。
   UI 卻把 node 當容器:`Single.tsx` 的 `{sn && <NodeTalk/>}` 讓「取消選取」等於卸載,
   對話與 sessionId 一起蒸發 —— 而後端那個 ClaudeSDKClient 還活著。
   再選一顆就是新 session,要重跑一次 `/story-discuss` 開場(~$0.13–0.24)。

   這兩條釘住錯配修好後的行為。第二條是花錢的那條。

   跑法(web/):  npm test -- talk-story-scope
*/
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import viz from "./fixtures/viz.json";

const spy = vi.hoisted(() => ({ stream: vi.fn() }));

vi.mock("../src/data/client", () => ({
  getStory: vi.fn(async () => ({ viz, source: "　　原文第一行。" })),
  getConclusions: vi.fn(async () => ({ conclusions: [] })),
  streamDiscuss: (...a: unknown[]) => {
    spy.stream(...a);
    return (async function* () {
      yield { event: "token", data: { text: `回答${spy.stream.mock.calls.length}` } };
      yield { event: "done", data: { ok: true, cost_usd: 0, session_id: "sid-1" } };
    })();
  },
  distillDiscuss: vi.fn(),
}));

import Single from "../src/journey/Single";

const KP = (viz as unknown as { feedback: { key_points: { title: string; refs: string[] }[] } }).feedback.key_points;

beforeEach(() => { vi.clearAllMocks(); });

async function openStory() {
  render(<MemoryRouter initialEntries={["/story/s02"]}>
    <Routes><Route path="/story/:slug" element={<Single />} /></Routes></MemoryRouter>);
  await waitFor(() => expect(document.querySelector("svg.bonestage")).toBeTruthy());
  fireEvent.click(screen.getByRole("button", { name: "回饋" }));
}

/** 點回饋條目的標題 = 開該節點的討論(Single.accItems 的既有行為) */
const selectNode = (i: number) => fireEvent.click(screen.getByText(KP[i].title));

async function send(text: string) {
  fireEvent.change(await screen.findByPlaceholderText(/說…/), { target: { value: text } });
  fireEvent.click(screen.getByText("↑"));
}

describe("討論的作用域是篇", () => {
  it("關掉討論框、改選另一顆節點,先前的對話還在", async () => {
    await openStory();
    selectNode(0);
    await send("這個比喻是不是落錯位置?");
    await waitFor(() => expect(screen.getByText("回答1")).toBeTruthy());

    fireEvent.click(screen.getByText("✕"));               // 取消選取
    await waitFor(() => expect(screen.queryByPlaceholderText(/說…/)).toBeNull());
    selectNode(1);                                        // 換一顆節點再開

    await waitFor(() => expect(screen.getByText("回答1")).toBeTruthy());
  });

  it("關掉再開不重開局:續用同一個 session,不再付一次開場成本", async () => {
    await openStory();
    selectNode(0);
    await send("第一句");
    await waitFor(() => expect(screen.getByText("回答1")).toBeTruthy());
    expect(spy.stream.mock.calls[0][1]).toBeNull();        // 第一輪本來就沒有 session

    fireEvent.click(screen.getByText("✕"));
    await waitFor(() => expect(screen.queryByPlaceholderText(/說…/)).toBeNull());
    selectNode(1);
    await send("第二句");

    await waitFor(() => expect(spy.stream).toHaveBeenCalledTimes(2));
    expect(spy.stream.mock.calls[1][1]).toBe("sid-1");     // 續局,不是新開
  });
});
