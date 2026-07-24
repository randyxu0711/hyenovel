import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import Dock from "../src/dock/Dock";
import type { VizData } from "../src/types";

const distillDiscuss = vi.fn();
vi.mock("../src/data/client", () => ({
  streamDiscuss: async function* () {
    yield { event: "message", data: { role: "assistant", text: "好", session_id: "sid-1" } };
    yield { event: "done", data: { ok: true, cost_usd: 0, session_id: "sid-1" } };
  },
  distillDiscuss: (...a: unknown[]) => distillDiscuss(...a),
}));

const viz = {
  slug: "x", title: "x", colors: {}, cn: {}, diag: {}, edges: [],
  nodes: [{ id: "t1", type: "theme", label: "訴說的不可能", note: "節點說明", intensity: null,
    evidence: [{ quote: "我們是披上層層雲幕", start: 12, end: 21, pos: 0.3 }] }],
  feedback: {
    read: "這篇在做什麼", one_line: "改這個", minor: [], strengths: [],
    key_points: [{ title: "關鍵", body: "獨白過大", question: "收一半會怎樣?", refs: ["t1"], quotes: [] }],
  },
} as unknown as VizData;

describe("Dock", () => {
  it("無選取顯示總覽", () => {
    render(<Dock slug="x" viz={viz} selected={null} />);
    expect(screen.getByText(/這篇在做什麼/)).toBeTruthy();
  });
  it("選 node 顯示其錨定回饋", () => {
    render(<Dock slug="x" viz={viz} selected="t1" />);
    expect(screen.getByText("訴說的不可能")).toBeTruthy();
    expect(screen.getByText(/獨白過大/)).toBeTruthy();
    expect(screen.getByText(/收一半會怎樣/)).toBeTruthy();
  });
  it("選到帶 evidence 的節點 → 列出引文且按鈕觸發 onJump(start,end)", () => {
    const onJump = vi.fn();
    const { container } = render(<Dock slug="x" viz={viz} selected="t1" onJump={onJump} />);
    expect(screen.getByText(/披上層層雲幕/)).toBeTruthy();
    fireEvent.click(container.querySelector(".dock-jump")!);
    expect(onJump).toHaveBeenCalledWith(12, 21);
  });

  it("minor 10:換故事要清掉上一篇的收束回報,不能帶到新故事裡", async () => {
    // fix pass 2 空包彈教訓:kept 只在 msgs.length>0 時才算繪,slug 的 effect 會清掉
    // msgs,所以 rerender 之後那塊本來就沒掛載 —— 拿掉 setKept("") 這條測試照樣綠。
    // 要在 rerender 之後、斷言之前於新故事送一則訊息,逼那塊重新掛載,才真的驗到 kept。
    distillDiscuss.mockResolvedValue({ written: 2, errors: [] });
    const { rerender } = render(<Dock slug="a" viz={viz} selected={null} />);

    fireEvent.change(screen.getByPlaceholderText(/寫下你的想法/), { target: { value: "測試訊息" } });
    fireEvent.click(screen.getByText("送出"));
    await waitFor(() => expect(screen.getByText("留下結論")).toBeTruthy());

    fireEvent.click(screen.getByText("留下結論"));
    await waitFor(() => expect(screen.getByText(/留下 2 條結論/)).toBeTruthy());

    // 換故事(同一顆 Dock 元件,slug 變了)
    rerender(<Dock slug="b" viz={viz} selected={null} />);

    // 在新故事送一則訊息,讓 dock-keep 那塊重新掛載 —— 若 kept 沒被清掉,
    // 舊故事的收束回報會在這裡重新冒出來(甚至還沒點過這次的「留下結論」)。
    fireEvent.change(screen.getByPlaceholderText(/寫下你的想法/), { target: { value: "故事 B 的話" } });
    fireEvent.click(screen.getByText("送出"));
    await waitFor(() => expect(screen.getByText("留下結論")).toBeTruthy());
    expect(screen.queryByText(/留下 2 條結論/)).toBeNull();
  });

  it("G4:session 死(reason=session_gone)→ 顯示冷卻字且鈕 disable", async () => {
    distillDiscuss.mockResolvedValue({ written: 0, errors: ["x"], reason: "session_gone" });
    render(<Dock slug="x" viz={viz} selected={null} />);
    fireEvent.change(screen.getByPlaceholderText(/寫下你的想法/), { target: { value: "嗨" } });
    fireEvent.click(screen.getByText("送出"));
    const keep = await screen.findByText("留下結論");
    fireEvent.click(keep);
    await waitFor(() => expect(screen.getByText(/討論已冷卻/)).toBeInTheDocument());
    expect(keep).toBeDisabled();
  });
});
