import { describe, test, expect } from "vitest";
import { formatResetHint } from "../src/journey/usageLimit";

describe("formatResetHint", () => {
  test("resets_at 秒 → 本地時刻文案", () => {
    const at = Math.floor(new Date("2026-07-08T14:30:00").getTime() / 1000);
    expect(formatResetHint(at)).toMatch(/14:30/);
  });
  test("resets_at 為 null → 泛用文案", () => {
    expect(formatResetHint(null)).toMatch(/稍後/);
  });
});
