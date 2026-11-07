import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Figure from "../src/dash/Figure";
import { draw } from "../src/dash/figure/draw";
import grammar from "../src/dash/figure/grammar.json";
import { expand, fallback, PENS, POSES, type FigureSpec } from "../src/dash/figure/poses";
import { ch, hyena } from "./dash-fixtures";

const builtin = (id: string): FigureSpec =>
  JSON.parse(readFileSync(join(__dirname, `../../marrow/prompts/characters/${id}.json`), "utf8")).figure;
const strokes = (spec: FigureSpec, size: number) => draw(spec, size, "s").groups.flatMap(([, list]) => list);

describe("文法", () => {
  it("和 den 用的文法檔同一份", () => {
    expect(grammar).toEqual(JSON.parse(readFileSync(join(__dirname, "../../marrow/figure.json"), "utf8")));
  });
});

describe("draw", () => {
  it("同一個種子畫出一樣的線,換種子就不同", () => {
    const spec = builtin("hyena");
    expect(draw(spec, 54, "a")).toEqual(draw(spec, 54, "a"));
    expect(draw(spec, 54, "a").groups).not.toEqual(draw(spec, 54, "b").groups);
  });
  it("姿態加上自己的部件;沒給眼睛就用姿態的", () => {
    const own = { group: "ears" as const, d: "M50 20 L60 10 L70 20 Z", fill: "second" as const };
    const out = expand({ pose: "mound", parts: [own], main: "olive", second: "bark" });
    expect(out.parts).toEqual([...POSES.mound.parts, own]);
    expect(out.eyes).toEqual(POSES.mound.eyes);
  });
  it("大尺寸用排線,32px 以下改平塗並拿掉細節", () => {
    const spec = builtin("hyena");
    expect(strokes(spec, 92).some(s => s.stroke === "var(--fig-main)")).toBe(true);
    const small = strokes(spec, 22);
    expect(small.some(s => s.stroke === "var(--fig-main)")).toBe(false);
    expect(small.some(s => s.fill === "var(--fig-main)")).toBe(true);
    expect(small.length).toBeLessThan(strokes(spec, 92).length);
  });
  it("描邊粗細換算回實際像素,不跟著縮放變粗", () => {
    const outline = (size: number) => strokes(builtin("deer"), size).find(s => s.stroke === "var(--fig-lead)")!.width * size / 120;
    expect(outline(92)).toBeCloseTo(1.3);
    expect(outline(54)).toBeCloseTo(1.1);
  });
});

describe("Figure", () => {
  it("內建角色畫自己的部件,群組有名字,帶狀態", () => {
    const c = { ...hyena, figure: builtin("hyena") };
    const { container } = render(<Figure character={c} state="speaking" size={54} />);
    const svg = container.querySelector("svg.fig")!;
    expect(svg.getAttribute("data-state")).toBe("speaking");
    expect(svg.getAttribute("data-who")).toBe("hyena");
    expect(svg.getAttribute("aria-hidden")).toBe("true");
    for (const g of ["legs", "tail", "body", "ears", "face", "eyes", "lips", "mouth"]) expect(svg.querySelector(`g.${g}`)).not.toBeNull();
    expect(svg.querySelectorAll("g.v0 g.eye.lid")).toHaveLength(2);
    expect(svg.getAttribute("style")).toContain("--fig-main: #cc8650");
  });
  it("沒有長相的角色用種子挑姿態和筆,同種子同長相", () => {
    expect(fallback("fox")).toEqual(fallback("fox"));
    expect(Object.keys(grammar.poses)).toContain(fallback("fox").pose);
    const { container } = render(<Figure character={ch("fox", "狐狸", "Fox", "zzz")} />);
    expect(container.querySelector("svg.fig g.body path")).not.toBeNull();
  });
  it("說話時線條在三組種子間換,其他狀態只畫一組", () => {
    const c = { ...hyena, figure: builtin("hyena") };
    const speaking = render(<Figure character={c} state="speaking" />).container;
    expect(speaking.querySelectorAll("g.v")).toHaveLength(3);
    const thinking = render(<Figure character={c} state="thinking" />).container;
    expect(thinking.querySelectorAll("g.v")).toHaveLength(1);
    expect(thinking.querySelectorAll("g.think > g")).toHaveLength(3);
    expect(thinking.querySelector("g.react path")).not.toBeNull();
  });
  it("節奏和招牌小動作寫在屬性上,沒給就是中速、不動", () => {
    const c = { ...hyena, figure: builtin("hyena") };
    const svg = render(<Figure character={c} />).container.querySelector("svg.fig")!;
    expect(svg.getAttribute("data-tempo")).toBe("quick");
    expect(svg.getAttribute("data-move")).toBe("tail-flick");
    const plain = render(<Figure character={ch("fox", "狐狸", "Fox", "zzz")} />).container.querySelector("svg.fig")!;
    expect(plain.getAttribute("data-tempo")).toBe("mid");
    expect(plain.hasAttribute("data-move")).toBe(false);
  });
  it("畫不出來的長相改用種子挑的預設,不讓整頁掛掉", () => {
    const broken = { ...hyena, figure: { parts: [{ group: "body" as const, d: "M--5 5 L20 20", fill: "main" as const }],
      eyes: [[1, 1], [2, 2]] as [[number, number], [number, number]], mouth: [[1, 1], [2, 2], [3, 3]] as [[number, number], [number, number], [number, number]],
      main: "olive" as const, second: "bark" as const } };
    const svg = render(<Figure character={broken} />).container.querySelector("svg.fig")!;
    expect(svg.querySelector("g.body path")).not.toBeNull();
    expect(svg.getAttribute("style")).toContain(`--fig-main: ${PENS[fallback(hyena.avatar.seed).main].light}`);
  });
  it("不給狀態就是 idle", () => {
    const { container } = render(<Figure character={hyena} />);
    expect(container.querySelector("svg.fig")!.getAttribute("data-state")).toBe("idle");
  });
});
