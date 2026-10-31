import { describe, it, expect } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

// 所有 CSS 打包在同一支 bundle:dash 的 class 名稱只要跟舊 web 的撞名,
// 對方的規則就會套進來(曾發生:lab.css 的 .talk 漸層蓋住 dash 對話欄)。
const SRC = join(__dirname, "..", "src");
const files = (readdirSync(SRC, { recursive: true }) as string[]).map(String);
const read = (f: string) => readFileSync(join(SRC, f), "utf8");

function dashClasses(): Set<string> {
  const out = new Set<string>();
  for (const f of files.filter(f => f.startsWith("dash") && f.endsWith(".tsx"))) {
    for (const m of read(f).matchAll(/className=(\{`[^`]*`\}|"[^"]*"|\{[^}]*\})/g))
      for (const c of m[1].match(/[a-z][a-z0-9-]+/g) ?? []) out.add(c);
  }
  return out;
}

describe("dash 的 class 不跟其他頁面的 CSS 撞名", () => {
  it("掃得到兩邊的檔(不是空轉)", () => {
    expect(files.filter(f => f.startsWith("dash") && f.endsWith(".tsx")).length).toBeGreaterThan(5);
    expect(files.filter(f => f.endsWith(".css") && !f.startsWith("dash")).length).toBeGreaterThan(0);
    expect(dashClasses().size).toBeGreaterThan(20);
  });
  it("沒有撞名", () => {
    const mine = dashClasses();
    const hits: string[] = [];
    for (const f of files.filter(f => f.endsWith(".css") && !f.startsWith("dash"))) {
      for (const [, c] of read(f).matchAll(/\.([a-zA-Z][\w-]*)/g)) if (mine.has(c)) hits.push(`${c} (${f})`);
    }
    expect([...new Set(hits)]).toEqual([]);
  });
});
