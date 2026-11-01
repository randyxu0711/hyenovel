import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { setLang } from "../src/dash/i18n";
import { makeCharacters } from "../src/dash/useCharacters";
import Avatar from "../src/dash/Avatar";
import { hyena, buffalo, deer, ch } from "./dash-fixtures";

const chars = makeCharacters([hyena, buffalo, deer], "hyena");

describe("useCharacters", () => {
  it("找得到就回那一位", () => {
    expect(chars.byId("deer").id).toBe("deer");
  });
  it("找不到:先同 mode,再預設,永遠回一個", () => {
    expect(chars.byId("gone", "direct").id).toBe("buffalo");
    expect(chars.byId("gone", "no-such-mode").id).toBe("hyena");
    expect(chars.byId("gone").id).toBe("hyena");
    expect(chars.byId(null).id).toBe("hyena");
  });
});

describe("Avatar", () => {
  it("內建 kind 畫 SVG,顏色吃角色的 --c-fill / --c-text", () => {
    const { container } = render(<Avatar character={deer} size={40} />);
    const svg = container.querySelector("svg")!;
    expect(svg.getAttribute("width")).toBe("40");
    expect(svg.style.getPropertyValue("--c-fill")).toMatch(/^#/);
  });
  it("未知 avatar.kind 不 crash,畫通用圖示的徽章", () => {
    setLang("zh-Hant");
    const { container } = render(<Avatar character={ch("fox", "slow", "狐狸", "Fox", "zzz")} />);
    const svg = container.querySelector("svg")!;
    expect(svg.getAttribute("data-kind")).toBe("zzz");
    expect(svg.querySelector("path, circle")).toBeTruthy();
  });
});
