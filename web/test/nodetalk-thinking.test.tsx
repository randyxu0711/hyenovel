import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import NodeTalk from "./talk-harness";
import type { VizNode } from "../src/types";

// 一輪真實形狀:先想一段(thinking),再開口(token),最後整輪收尾(message)。
vi.mock("../src/data/client", () => ({
  streamDiscuss: async function* () {
    yield { event: "thinking", data: { text: "先確認 m2 " } };
    yield { event: "thinking", data: { text: "在原文出現幾次" } };
    yield { event: "token", data: { text: "我不認為 m2 " } };
    yield { event: "token", data: { text: "用得太滿。" } };
    yield { event: "message", data: { role: "assistant", text: "我不認為 m2 用得太滿。", session_id: "sid-1" } };
    yield { event: "done", data: { ok: true, cost_usd: 0, session_id: "sid-1" } };
  },
  distillDiscuss: vi.fn(),
}));

const node: VizNode = { id: "m2", type: "motif", label: "破帽", note: "", intensity: null, evidence: [] };

const mount = () => render(<NodeTalk slug="s1" node={node} typeName="意象" color="#a98bb8" flag=""
  kp={null} onClose={() => {}} />);

async function send() {
  fireEvent.change(screen.getByPlaceholderText(/說…/), { target: { value: "這意象是不是用得太滿?" } });
  fireEvent.click(screen.getByText("↑"));
}

describe("NodeTalk 思考可見化", () => {
  it("thinking 串進畫面,且不混進回答本體", async () => {
    const { container } = mount();
    await send();
    await waitFor(() => expect(container.querySelector(".talk-think")).toBeTruthy());
    const think = container.querySelector(".talk-think")!;
    expect(think.textContent).toBe("先確認 m2 在原文出現幾次");
    // 回答本體只有回答 —— 兩者混在一起,存進 transcript 的正本就會跟畫面對不上。
    // 把 .talk-think 摘掉再看剩下什麼:這才問得到「思考有沒有滲進回答」,
    // 而不是問到那個同時包著兩者的外層 .talk-line。
    await waitFor(() => expect(container.querySelector(".talk-line.ed")!.textContent).toContain("我不認為"));
    const line = container.querySelector(".talk-line.ed")!.cloneNode(true) as HTMLElement;
    line.querySelector(".talk-think")!.remove();
    expect(line.textContent).toBe("我不認為 m2 用得太滿。");
  });

  it("思考一開始流,等待提示就退場(它本來就是「什麼都沒有」的替身)", async () => {
    const { container } = mount();
    await send();
    await waitFor(() => expect(container.querySelector(".talk-think")).toBeTruthy());
    expect(container.querySelector(".talk-wait")).toBeNull();
  });

  it("思考留在那一則旁邊,不會被後來的回答蓋掉", async () => {
    const { container } = mount();
    await send();
    await waitFor(() => expect(screen.getByText("我不認為 m2 用得太滿。")).toBeTruthy());
    expect(container.querySelector(".talk-think")!.textContent).toBe("先確認 m2 在原文出現幾次");
  });
});
