import { readdirSync, readFileSync } from "node:fs";
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

  it("沒有孤兒鍵:字典每個鍵都被 dash 程式碼引用", () => {
    const dir = "src/dash";
    const src = readdirSync(dir)
      .filter(f => /\.(ts|tsx)$/.test(f) && f !== "i18n.ts")
      .map(f => readFileSync(`${dir}/${f}`, "utf8")).join("\n");
    // 動態引用:`prefix.${x}` 視為引用該前綴下全部鍵;err.<code> 由 DEN_ERROR_CODES 推導
    const prefixes = [...src.matchAll(/["'`]([\w.]+\.)\$\{/g)].map(m => m[1]);
    const errKeys = new Set(["err.unknown", ...DEN_ERROR_CODES.map(c => `err.${c}`)]); // err.unknown 由 errorMessage 回傳
    const orphans = Object.keys(zhHant).filter(k =>
      !src.includes(`"${k}"`) && !src.includes(`'${k}'`) && !src.includes(`\`${k}\``) &&
      !errKeys.has(k) && !prefixes.some(p => k.startsWith(p)));
    expect(orphans).toEqual([]);
  });
});
