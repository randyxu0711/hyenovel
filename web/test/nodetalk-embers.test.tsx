import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import NodeTalk from "../src/lab/NodeTalk";
import type { VizNode, Conclusion } from "../src/types";

const distillDiscuss = vi.fn();
vi.mock("../src/data/client", () => ({
  streamDiscuss: async function* () {
    yield { event: "message", data: { role: "assistant", text: "好", session_id: "sid-1" } };
    yield { event: "done", data: { ok: true, cost_usd: 0, session_id: "sid-1" } };
  },
  distillDiscuss: (...a: unknown[]) => distillDiscuss(...a),
}));

const node: VizNode = { id: "m1", type: "motif", label: "破帽", note: "", intensity: null, evidence: [] };
const cs: Conclusion[] = [
  { id: "c1", kind: "observation", text: "活的結論", refs: ["m1"], quotes: ["原句"], stale: false },
  { id: "c2", kind: "judgment", text: "冷的結論", refs: ["m1"], quotes: [], stale: true },
];

const mount = (props: Partial<React.ComponentProps<typeof NodeTalk>> = {}) =>
  render(<NodeTalk slug="s1" node={node} typeName="意象" color="#a98bb8" flag=""
    kp={null} onClose={() => {}} {...props} />);

// 送一則訊息把 talk-keep 那塊逼出來(鈕受 msgs.length>0 閘控)
async function sendOne(text: string) {
  fireEvent.change(screen.getByPlaceholderText(/說…/), { target: { value: text } });
  fireEvent.click(screen.getByText("↑"));
  await waitFor(() => expect(screen.getByText("留下結論")).toBeTruthy());
}

describe("NodeTalk 餘燼塊", () => {
  it("顯示過去結論、活在前冷在後、冷的帶 stale class", () => {
    const { container } = mount({ conclusions: cs });
    expect(screen.getByText("活的結論")).toBeTruthy();
    expect(screen.getByText("冷的結論")).toBeTruthy();
    const notes = container.querySelectorAll(".ember-note");
    expect(notes[0].className).toContain("live");    // 活在前
    expect(notes[1].className).toContain("stale");
  });
  it("沒有結論就整塊不出現(無空狀態、無交代性文字)", () => {
    const { container } = mount();
    expect(container.querySelector(".talk-embers")).toBeNull();
  });
});

// 以下兩條自 dock.test.tsx 移植:keep() 從 Dock 搬進 NodeTalk,這兩條政策
// (換篇清收束回報 / session 死掉的冷卻鈕)得跟著搬,否則刪 Dock 就沒人守。
describe("NodeTalk 留下結論", () => {
  it("written>0 → 回報條數並呼叫 onKept(通知 Single refetch 長出新燼)", async () => {
    distillDiscuss.mockResolvedValue({ written: 2, errors: [] });
    const onKept = vi.fn();
    mount({ onKept });
    await sendOne("測試訊息");
    fireEvent.click(screen.getByText("留下結論"));
    await waitFor(() => expect(screen.getByText(/留下 2 條結論/)).toBeTruthy());
    expect(onKept).toHaveBeenCalled();
  });

  it("換故事要清掉上一篇的收束回報,不能帶到新故事裡", async () => {
    // 空包彈教訓(承自 dock.test):kept 只在 msgs.length>0 時才繪,而換 slug 的
    // effect 本來就清掉 msgs → 不在新故事再送一則訊息,拿掉 setKept("") 也照樣綠。
    distillDiscuss.mockResolvedValue({ written: 2, errors: [] });
    const { rerender } = mount();
    await sendOne("測試訊息");
    fireEvent.click(screen.getByText("留下結論"));
    await waitFor(() => expect(screen.getByText(/留下 2 條結論/)).toBeTruthy());

    rerender(<NodeTalk slug="s2" node={node} typeName="意象" color="#a98bb8" flag=""
      kp={null} onClose={() => {}} />);
    await sendOne("故事 B 的話");
    expect(screen.queryByText(/留下 2 條結論/)).toBeNull();
  });

  it("G4:session 死(reason=session_gone)→ 顯示冷卻字且鈕 disable", async () => {
    distillDiscuss.mockResolvedValue({ written: 0, errors: ["x"], reason: "session_gone" });
    mount();
    await sendOne("嗨");
    const keep = screen.getByText("留下結論");
    fireEvent.click(keep);
    await waitFor(() => expect(screen.getByText(/討論已冷卻/)).toBeInTheDocument());
    expect(keep).toBeDisabled();
  });
});
