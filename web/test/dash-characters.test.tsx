import { describe, it, expect } from "vitest";
import { makeCharacters } from "../src/dash/useCharacters";
import { hyena, buffalo, deer } from "./dash-fixtures";

const chars = makeCharacters([hyena, buffalo, deer], "hyena");

describe("useCharacters", () => {
  it("找得到就回那一位", () => {
    expect(chars.byId("deer").id).toBe("deer");
  });
  it("active 不含已封存;byId 仍查得到,舊發言才顯示得出名字", () => {
    const gone = { ...deer, id: "u1", origin: "imported" as const, archived: true };
    const c = makeCharacters([hyena, gone], "hyena");
    expect(c.active.map(x => x.id)).toEqual(["hyena"]);
    expect(c.byId("u1").id).toBe("u1");
  });
  it("找不到:退回預設,永遠回一個", () => {
    expect(chars.byId("gone").id).toBe("hyena");
    expect(chars.byId(null).id).toBe("hyena");
  });
});
