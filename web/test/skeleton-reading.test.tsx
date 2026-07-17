import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import Skeleton from "../src/viz/Skeleton";
import type { VizData, VizNode } from "../src/types";

// 「秤出輕重」的政策:掃描光沿脊椎跑,節點要**正好**在光走到自己那根肋時亮。
// 對不上就退化成兩組各跑各的裝飾 —— 而「亮起的順序 = 讀者遇到它們的順序」正是這動畫的全部意義。
// 同步靠 animation-delay(由 evidence.pos 換算)+ 同週期,jsdom 不跑動畫但算得出 delay。

const beat = (id: string, intensity: number): VizNode =>
  ({ id, type: "beat", label: id, note: "", intensity, evidence: [] });
const at = (id: string, pos: number): VizNode =>
  ({ id, type: "motif", label: id, note: "", intensity: null,
     evidence: [{ quote: "x", start: 0, end: 1, pos }] });

// 三個意象分別落在原文的 0% / 50% / 100%
const viz: VizData = {
  slug: "s", title: "t",
  nodes: [beat("b1", 0.4), beat("b2", 0.5), at("head", 0), at("mid", 0.5), at("tail", 1)],
  edges: [{ type: "precedes", from: "b1", to: "b2" }],
  colors: {}, cn: {}, diag: {}, feedback: null,
};

const delays = (c: HTMLElement) =>
  [...c.querySelectorAll<SVGElement>(".node")].map(n => parseFloat(n.style.animationDelay));

describe("Skeleton — 秤出輕重(reading)", () => {
  it("不在 reading 時沒有掃描光,也不給節點 delay", () => {
    const { container } = render(<Skeleton viz={viz} width={300} />);
    expect(container.querySelector(".read-sweep")).toBeNull();
    expect(delays(container).every(d => Number.isNaN(d))).toBe(true);
  });

  it("reading 時長出掃描光", () => {
    const { container } = render(<Skeleton viz={viz} width={300} reading />);
    expect(container.querySelector(".read-sweep")).toBeTruthy();
  });

  it("節點的 delay 依原文位置遞增 —— 亮起的順序就是讀者遇到它們的順序", () => {
    const { container } = render(<Skeleton viz={viz} width={300} reading />);
    const [head, mid, tail] = delays(container);
    expect(head).toBeLessThan(mid);
    expect(mid).toBeLessThan(tail);
  });

  it("delay 對得上掃描光的到達時刻(補掉 -.06→1 的總程與閃光的 5% 偏移)", () => {
    const { container } = render(<Skeleton viz={viz} width={300} reading />);
    const [head, mid, tail] = delays(container);
    const CYCLE = 4.4;
    // 掃描段的起點跑 -.06 → 1(總程 1.06);它抵達相對位置 p 的時刻:
    const arrive = (p: number) => ((p + 0.06) / 1.06) * CYCLE;
    // 節點閃光落在自己週期的 5% → 實際亮起時刻 = delay + .05*CYCLE
    const flash = (d: number) => d + 0.05 * CYCLE;
    expect(flash(head)).toBeCloseTo(arrive(0), 1);
    expect(flash(mid)).toBeCloseTo(arrive(0.5), 1);
    expect(flash(tail)).toBeCloseTo(arrive(1), 1);
  });

  it("ignite 與 reading 不同時掛:兩者都動 .node,同掛會被 CSS 疊掉一個", () => {
    const { container } = render(<Skeleton viz={viz} width={300} ignite reading />);
    const svg = container.querySelector(".skel")!;
    expect(svg.classList.contains("ignite")).toBe(true);
    expect(svg.classList.contains("reading")).toBe(false);
  });
});
