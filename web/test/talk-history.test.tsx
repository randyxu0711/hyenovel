/* F5 之後,畫面接得回過去的逐字。

   P1 起 `transcript.jsonl` 就逐輪寫著正本,但前端從沒讀過它 ——「討論不再蒸發」
   在後端成立、在使用者眼裡沒成立:重整一次,昨天聊的東西在磁碟上完好無缺,
   畫面上一個字都沒有。

   同時釘住一條政策:
   邊界要誠實。開新局時模型拿到的是 `recall` 注入的**蒸餾結論**(discuss.py:90),
   不是這些逐字。畫面顯示歷史不等於編輯讀過歷史,那句話要寫在畫面上。

   跑法(web/):  npm test -- talk-history
*/
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import NodeTalk from "./talk-harness";
import type { VizNode } from "../src/types";

const h = vi.hoisted(() => ({
  getTranscript: vi.fn(async () => ({
    turns: [
      { ts: 1, session: "a1", role: "user", text: "過去的問題", anchors: ["m2"] },
      { ts: 2, session: "a1", role: "assistant", text: "過去的回答", anchors: ["m2"] },
    ],
  })),
}));

vi.mock("../src/data/client", () => ({
  getTranscript: (...a: unknown[]) => h.getTranscript(...(a as [])),
  streamDiscuss: () => (async function* () {
    yield { event: "token", data: { text: "現在的回答" } };
    yield { event: "done", data: { ok: true, cost_usd: 0, session_id: "sid-1" } };
  })(),
}));

const node: VizNode = { id: "m2", type: "motif", label: "破帽", note: "", intensity: null, evidence: [] };
const mount = () => render(<NodeTalk slug="s1" node={node} typeName="意象" color="#a98bb8"
  flag="" kp={null} onClose={() => {}} />);

beforeEach(() => { vi.clearAllMocks(); });

describe("討論的逐字歷史", () => {
  it("重新進來就把過去的對話畫回來(正本一直在,只是沒人讀)", async () => {
    mount();
    await waitFor(() => expect(screen.getByText("過去的問題")).toBeTruthy());
    expect(screen.getByText("過去的回答")).toBeTruthy();
  });

  it("過去與現在之間有邊界,且它講明編輯不重讀這些字", async () => {
    const { container } = mount();
    const b = await waitFor(() => {
      const el = container.querySelector(".talk-boundary");
      expect(el).toBeTruthy();
      return el!;
    });
    expect(b.textContent).toMatch(/不重讀/);
  });

  it("讀不到歷史不擋討論(歷史是增益不是主線,同燼的處置)", async () => {
    h.getTranscript.mockRejectedValueOnce(new Error("boom"));
    mount();
    fireEvent.change(await screen.findByPlaceholderText(/說…/), { target: { value: "照樣能聊" } });
    fireEvent.click(screen.getByText("↑"));
    await waitFor(() => expect(screen.getByText("現在的回答")).toBeTruthy());
  });
});
