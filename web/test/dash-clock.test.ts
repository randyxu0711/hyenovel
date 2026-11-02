import { describe, it, expect } from "vitest";
import { clock, stepOf } from "../src/dash/clock";

describe("clock", () => {
  it("m:ss,分鐘不進位成小時", () => {
    expect(clock(0)).toBe("0:00");
    expect(clock(59)).toBe("0:59");
    expect(clock(61)).toBe("1:01");
    expect(clock(3725)).toBe("62:05");
    expect(clock(65.9)).toBe("1:05");
  });
  it("負數或 NaN → 0:00", () => {
    expect(clock(-3)).toBe("0:00");
    expect(clock(NaN)).toBe("0:00");
  });
});

describe("stepOf", () => {
  it("SSE 步驟優先,沒有就看作品 state", () => {
    expect(stepOf(null, "running")).toBe("observe");
    expect(stepOf(null, "notes-running")).toBe("notes");
    expect(stepOf("analyst", "notes-running")).toBe("observe");
    expect(stepOf("reviewer", "running")).toBe("notes");
  });
});
