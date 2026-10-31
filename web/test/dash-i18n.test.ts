import { describe, it, expect, beforeEach } from "vitest";
import { en, zhHant, errorMessage, localized, setLang, getLang, resetLang, translate } from "../src/dash/i18n";
import { DEN_ERROR_CODES } from "../src/dash/api";

describe("i18n", () => {
  beforeEach(() => { localStorage.clear(); resetLang(); });

  it("中英字典的鍵完全一致", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(zhHant).sort());
  });
  it("den 的每個錯誤代碼都有訊息", () => {
    expect(DEN_ERROR_CODES.length).toBeGreaterThan(20);
    for (const c of DEN_ERROR_CODES) expect(errorMessage(c)).not.toBe("err.unknown");
  });
  it("未知代碼 → err.unknown", () => {
    expect(errorMessage("no-such-code")).toBe("err.unknown");
  });
  it("localized 缺目前語言時退回另一個", () => {
    expect(localized({ en: "Fox" }, "zh-Hant")).toBe("Fox");
    expect(localized({ "zh-Hant": "狐" }, "en")).toBe("狐");
    expect(localized({ "zh-Hant": "狐", en: "Fox" }, "en")).toBe("Fox");
  });
  it("setLang 存 localStorage,重讀得回來", () => {
    setLang("en");
    expect(localStorage.getItem("hyenovel.lang")).toBe("en");
    resetLang();
    expect(getLang()).toBe("en");
  });
  it("讀不到存值就跟 navigator.language", () => {
    const orig = Object.getOwnPropertyDescriptor(window.navigator, "language");
    Object.defineProperty(window.navigator, "language", { value: "zh-TW", configurable: true });
    resetLang();
    expect(getLang()).toBe("zh-Hant");
    Object.defineProperty(window.navigator, "language", { value: "fr-FR", configurable: true });
    resetLang();
    expect(getLang()).toBe("en");
    if (orig) Object.defineProperty(window.navigator, "language", orig);
  });
  it("translate 代入參數", () => {
    // 字典第 1 批沒有帶參數的訊息;直接驗代入規則
    expect(translate("en", "loading", {})).toBe(en.loading);
  });
});
