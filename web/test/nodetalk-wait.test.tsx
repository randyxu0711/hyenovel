/* 送出之後、第一個 token 之前,畫面必須說話。

   這是政策不是裝飾:討論關掉 extended thinking 之後單輪仍要 20 秒起跳,
   而那段時間前端**收不到任何事件**。原本只有一個不會動的「…」,使用者讀到的是
   「壞了」而不是「在忙」(2026-07-27 使用者回報)。這組測試釘住那段空窗有東西在。

   跑法(web/):  npm test -- nodetalk-wait
*/
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import NodeTalk from "./talk-harness";
import type { VizNode } from "../src/types";

// 用一道閘把第一個 token 擋在外面 —— 那正是真實情況裡「後端在跑、前端沒事件」的那 20 秒。
const gate = vi.hoisted(() => {
  let open!: () => void;
  const waited = new Promise<void>(r => { open = r; });
  return { waited, open: () => open() };
});

vi.mock("../src/data/client", () => ({
  streamDiscuss: async function* () {
    await gate.waited;
    yield { event: "token", data: { text: "我不認為 m2 用得太滿。" } };
    yield { event: "done", data: { ok: true, cost_usd: 0, session_id: "sid-1" } };
  },
  distillDiscuss: vi.fn(),
}));

const node: VizNode = { id: "m2", type: "motif", label: "破帽", note: "", intensity: null, evidence: [] };

describe("NodeTalk 等待狀態", () => {
  it("送出後就有等待提示,而且它自己講得出在等什麼", async () => {
    const { container } = render(<NodeTalk slug="s1" node={node} typeName="意象" color="#a98bb8"
      flag="" kp={null} onClose={() => {}} />);
    fireEvent.change(screen.getByPlaceholderText(/說…/), { target: { value: "這意象是不是用得太滿?" } });
    fireEvent.click(screen.getByText("↑"));

    const wait = await waitFor(() => {
      const el = container.querySelector(".talk-wait");
      expect(el).toBeTruthy();
      return el!;
    });
    // 意義要掛在字上:減動會把那三顆點停住,只剩這行字撐著。空的等待提示等於沒有等待提示。
    expect(wait.textContent).toContain("編輯正在回應");
    // 讀螢幕的人也要收得到這個轉場,不然「空掛著」對他們照樣成立。
    expect(wait.getAttribute("aria-live")).toBe("polite");

    // 第一個 token 一到,等待提示讓位給回答 —— 兩個不該並存。
    gate.open();
    await waitFor(() => expect(screen.getByText("我不認為 m2 用得太滿。")).toBeTruthy());
    expect(container.querySelector(".talk-wait")).toBeNull();
  });
});
