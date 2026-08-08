/* 討論框渲染編輯打的 markdown —— 但只渲染編輯那一側。

   實測 9 則回覆 5,977 字裡有 55 個 `**粗體**`、14 個 `---`,以裸標記顯示。
   走 JSON schema + 閘門的通道(feedback / analysis / conclusions)全部零標記;
   唯一無約束的自由散文通道長滿標記 —— 那不是模型的壞習慣,是通道有沒有形狀的結果。
   本輪的立場是**在 view 層渲染它**,不在 prompt 裡叫它別打(那類軟約束的失敗是沉默的)。

   這裡測的是**我們的政策**,不是 react-markdown 會不會解析 `**`:
   ① 編輯側渲染 ② 使用者側不渲染 ③ past 與 msgs 同一套規則(否則同一句話在歷史區是
   裸 `**`、在當局是粗體)。

   跑法(web/):  npm test -- talk-markdown
*/
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import NodeTalk from "./talk-harness";
import type { VizNode } from "../src/types";

const h = vi.hoisted(() => ({
  getTranscript: vi.fn(async () => ({
    turns: [
      { ts: 1, session: "a1", role: "user", text: "歷史裡**使用者**打的星號", anchors: ["m2"] },
      { ts: 2, session: "a1", role: "assistant", text: "歷史裡**編輯**打的星號", anchors: ["m2"] },
    ],
  })),
}));

vi.mock("../src/data/client", () => ({
  getTranscript: (...a: unknown[]) => h.getTranscript(...(a as [])),
  streamDiscuss: () => (async function* () {
    yield { event: "token", data: { text: "這一局**編輯**的強調" } };
    yield { event: "done", data: { ok: true, cost_usd: 0, session_id: "sid-1" } };
  })(),
}));

const node: VizNode = { id: "m2", type: "motif", label: "破帽", note: "", intensity: null, evidence: [] };
const mount = () => render(<NodeTalk slug="s1" node={node} typeName="意象" color="#a98bb8"
  flag="" kp={null} onClose={() => {}} />);

/** 送一則使用者訊息並等編輯回完 —— msgs 兩側同時就位才驗得到「同一棵 DOM 上兩套規則」。 */
async function talk(userText: string) {
  const { container } = mount();
  await waitFor(() => expect(container.querySelector(".talk-line.past")).toBeTruthy());
  fireEvent.change(screen.getByPlaceholderText(/說…/), { target: { value: userText } });
  fireEvent.click(screen.getByText("↑"));
  await waitFor(() => expect(container.querySelector(".talk-line.ed:not(.past)")?.textContent)
    .toMatch(/強調/));
  return container;
}

const live = (c: HTMLElement, side: "me" | "ed") =>
  c.querySelector<HTMLElement>(`.talk-line.${side}:not(.past)`)!;
const history = (c: HTMLElement, side: "me" | "ed") =>
  c.querySelector<HTMLElement>(`.talk-line.past.${side}`)!;

beforeEach(() => { vi.clearAllMocks(); });

describe("討論框的 markdown", () => {
  it("編輯側渲染:`**x**` 變 <strong>,裸星號不留在畫面上", async () => {
    const c = await talk("問一句");
    const ed = live(c, "ed");
    expect(ed.querySelector("strong")?.textContent).toBe("編輯");
    expect(ed.textContent).not.toContain("**");
  });

  it("使用者側不渲染:使用者寫的是純文學,`*` 可能就是他要的那個字", async () => {
    const c = await talk("我打的**星號**要原樣留著");
    const me = live(c, "me");
    expect(me.querySelector("strong")).toBeNull();
    expect(me.textContent).toContain("**星號**");
  });

  it("past 與 msgs 同一套規則(只做一邊會讓同一句話在兩區長得不一樣)", async () => {
    const c = await talk("問一句");
    expect(history(c, "ed").querySelector("strong")?.textContent).toBe("編輯");
    expect(history(c, "ed").textContent).not.toContain("**");
    expect(history(c, "me").querySelector("strong")).toBeNull();
    expect(history(c, "me").textContent).toContain("**使用者**");
  });
});
