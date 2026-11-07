import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const root = join(__dirname, "..");
const html = readFileSync(join(root, "index.html"), "utf8");

describe("品牌", () => {
  it("分頁標題只叫 Hyenovel,不用中文名", () => {
    expect(html).toMatch(/<title>Hyenovel<\/title>/);
    expect(html).not.toContain("鬣文");
  });
  it("分頁縮圖指向 public 裡存在的 SVG,且晝夜會換色", () => {
    const href = html.match(/<link rel="icon" type="image\/svg\+xml" href="\/([^"]+)"/)![1];
    const file = join(root, "public", href);
    expect(existsSync(file)).toBe(true);
    expect(readFileSync(file, "utf8")).toContain("prefers-color-scheme:dark");
  });
});
