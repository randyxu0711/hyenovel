import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import NodeTalk from "./talk-harness";
import type { VizNode, Conclusion } from "../src/types";

vi.mock("../src/data/client", () => ({
  getTranscript: vi.fn(async () => ({ turns: [] })),
  streamDiscuss: async function* () {
    yield { event: "message", data: { role: "assistant", text: "好", session_id: "sid-1" } };
    yield { event: "done", data: { ok: true, cost_usd: 0, session_id: "sid-1" } };
  },
}));

const node: VizNode = { id: "m1", type: "motif", label: "破帽", note: "", intensity: null, evidence: [] };
const cs: Conclusion[] = [
  { id: "c1", kind: "observation", text: "活的結論", refs: ["m1"], quotes: ["原句"], stale: false },
  { id: "c2", kind: "judgment", text: "冷的結論", refs: ["m1"], quotes: [], stale: true },
];

const mount = (props: Partial<React.ComponentProps<typeof NodeTalk>> = {}) =>
  render(<NodeTalk slug="s1" node={node} typeName="意象" color="#a98bb8" flag=""
    kp={null} onClose={() => {}} {...props} />);

describe("NodeTalk 餘燼塊", () => {
  it("預設收起:只出把手,不吐內文(定向區先讓給編輯的判斷)", () => {
    const { container } = mount({ conclusions: cs });
    expect(screen.queryByText("活的結論")).toBeNull();
    expect(container.querySelector(".talk-embers")).toBeTruthy();
  });
  it("把手用一排火花講條數與活冷,零交代性文字", () => {
    const { container } = mount({ conclusions: cs });
    const sparks = container.querySelectorAll(".ember-spark");
    expect(sparks.length).toBe(2);                          // 幾條就幾顆
    expect(sparks[0].classList.contains("live")).toBe(true);
    expect(sparks[1].classList.contains("stale")).toBe(true);
    expect(container.querySelector(".talk-embers")!.textContent).not.toMatch(/\d/);  // 不報數字
  });
  it("點把手展開:活在前冷在後、冷的帶 stale class", () => {
    const { container } = mount({ conclusions: cs });
    fireEvent.click(container.querySelector(".talk-embers-h")!);
    expect(screen.getByText("活的結論")).toBeTruthy();
    expect(screen.getByText("冷的結論")).toBeTruthy();
    const notes = container.querySelectorAll(".ember-note");
    expect(notes[0].className).toContain("live");    // 活在前
    expect(notes[1].className).toContain("stale");
  });
  it("結論塊不在定向區(talk-standing)裡——它該挨著輸入框", () => {
    const { container } = mount({ conclusions: cs });
    expect(container.querySelector(".talk-standing .talk-embers")).toBeNull();
    expect(container.querySelector(".talk-body > .talk-embers")).toBeTruthy();
  });
  it("沒有結論就整塊不出現(無空狀態、無交代性文字)", () => {
    const { container } = mount();
    expect(container.querySelector(".talk-embers")).toBeNull();
  });
});
