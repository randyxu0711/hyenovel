import { describe, test, expect } from "vitest";
import { formatResetTime } from "../src/journey/usageLimit";

describe("formatResetTime", () => {
  test("resets_at 秒 → 本地 24h HH:MM", () => {
    const at = Math.floor(new Date("2026-07-08T14:30:00").getTime() / 1000);
    expect(formatResetTime(at)).toBe("14:30");
  });
  test("resets_at 為 null → null(泛用句由呼叫端給)", () => {
    expect(formatResetTime(null)).toBeNull();
  });
});
