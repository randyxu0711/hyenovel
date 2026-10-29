/* 失敗的一輪不能長得像正常回答:den 整輪成功才落盤,其餘 = 沒發生過。 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import NodeTalk from "./talk-harness";
import type { VizNode } from "../src/types";

const h = vi.hoisted(() => ({ events: [] as { event: string; data: Record<string, unknown> }[] }));

vi.mock("../src/data/client", () => ({
  getTranscript: async () => ({ turns: [] }),
  streamDiscuss: () => (async function* () { for (const e of h.events) yield e; })(),
}));

const node: VizNode = { id: "m2", type: "motif", label: "破帽", note: "", intensity: null, evidence: [] };

async function run(events: typeof h.events) {
  h.events = events;
  const { container } = render(<NodeTalk slug="s1" node={node} typeName="意象" color="#a98bb8"
    flag="" kp={null} onClose={() => {}} />);
  fireEvent.change(screen.getByPlaceholderText(/說…/), { target: { value: "問" } });
  fireEvent.click(screen.getByText("↑"));
  return container;
}

beforeEach(() => { h.events = []; });

describe("失敗的一輪", () => {
  it("token 之後 error:留下半截字,並標示沒存下", async () => {
    const c = await run([{ event: "token", data: { text: "半截" } },
      { event: "error", data: { where: "discuss", message: "逾時", recoverable: true } }]);
    await waitFor(() => expect(c.textContent).toContain("沒有存下"));
    expect(c.textContent).toContain("半截");
    expect(c.textContent).toContain("逾時");
  });

  it("token 之後串流無聲結束:同樣標示沒存下", async () => {
    const c = await run([{ event: "token", data: { text: "半截" } }]);
    await waitFor(() => expect(c.textContent).toContain("沒有存下"));
  });

  it("沒有 token 就 error:維持原本的出錯文字", async () => {
    const c = await run([{ event: "error", data: { where: "discuss", message: "掛了", recoverable: false } }]);
    await waitFor(() => expect(c.textContent).toContain("(討論出錯:掛了)"));
  });

  it("正常 token→message→done:不標示,並以 message.text 為準", async () => {
    const c = await run([{ event: "token", data: { text: "草" } },
      { event: "message", data: { role: "assistant", text: "存下的版本", session_id: "s" } },
      { event: "done", data: { ok: true, session_id: "s" } }]);
    await waitFor(() => expect(c.textContent).toContain("存下的版本"));
    expect(c.textContent).not.toContain("沒有存下");
  });
});
