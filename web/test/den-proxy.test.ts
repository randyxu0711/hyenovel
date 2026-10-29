// @vitest-environment node
import { describe, it, expect, vi } from "vitest";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { dataDir, denTarget, denProxy, DEN_DOWN } from "../den-proxy";

function mkdir(files: Record<string, string>) {
  const d = mkdtempSync(join(tmpdir(), "den-"));
  for (const [k, v] of Object.entries(files)) writeFileSync(join(d, k), v);
  return d;
}
const full = { "den.json": JSON.stringify({ port: 8790, pid: 1, version: "v" }), "den.token": "tok123\n" };

describe("dataDir", () => {
  it("XDG_DATA_HOME 優先", () => {
    expect(dataDir({ XDG_DATA_HOME: "/x" } as any)).toBe("/x/hyenovel");
  });
  it("否則 ~/.local/share/hyenovel", () => {
    expect(dataDir({} as any)).toMatch(/\.local\/share\/hyenovel$/);
  });
});

describe("denTarget", () => {
  it("齊全 → url + 去空白 token", () => {
    expect(denTarget(mkdir(full))).toEqual({ url: "http://127.0.0.1:8790", token: "tok123" });
  });
  it("缺 den.json → null", () => {
    expect(denTarget(mkdir({ "den.token": "t" }))).toBeNull();
  });
  it("缺 token → null", () => {
    expect(denTarget(mkdir({ "den.json": full["den.json"] }))).toBeNull();
  });
});

/** 拿到 configure 包過的 web():底層 web 是 spy。 */
function harness(dir: string) {
  const inner = vi.fn();
  const proxy: any = { web: inner };
  const opts = denProxy(dir);
  (opts.configure as any)(proxy, opts);
  const res: any = {
    statusCode: 0, headers: {} as any, body: "",
    setHeader(k: string, v: string) { this.headers[k] = v; },
    end(b: string) { this.body = b; },
  };
  const call = (headers: Record<string, string>) => {
    const req: any = { headers: { host: "localhost:5173", ...headers }, url: "/stories" };
    proxy.web(req, res, {});
    return req;
  };
  return { inner, res, call, opts };
}

describe("denProxy", () => {
  it("rewrite 去掉 /api", () => {
    expect(harness(mkdir(full)).opts.rewrite!("/api/stories")).toBe("/stories");
  });
  it("同源 Origin:設 Authorization、移除 origin、target 為 den", () => {
    const h = harness(mkdir(full));
    const req = h.call({ origin: "http://localhost:5173" });
    expect(h.inner).toHaveBeenCalledOnce();
    const o = h.inner.mock.calls[0][2];
    expect(o.target).toBe("http://127.0.0.1:8790");
    expect(o.headers.Authorization).toBe("Bearer tok123");
    expect(req.headers.origin).toBeUndefined();
  });
  it("外來 Origin → 403 且不轉發", () => {
    const h = harness(mkdir(full));
    h.call({ origin: "http://evil.example" });
    expect(h.res.statusCode).toBe(403);
    expect(h.inner).not.toHaveBeenCalled();
  });
  it("無 Origin 放行", () => {
    const h = harness(mkdir(full));
    h.call({});
    expect(h.inner).toHaveBeenCalledOnce();
  });
  it("每個請求重讀:den 換 port 後跟著走", () => {
    const dir = mkdir(full);
    const h = harness(dir);
    writeFileSync(join(dir, "den.json"), JSON.stringify({ port: 9001 }));
    h.call({});
    expect(h.inner.mock.calls[0][2].target).toBe("http://127.0.0.1:9001");
  });
  it("den 沒在跑 → 503 JSON,不轉發", () => {
    const h = harness(mkdir({}));
    h.call({});
    expect(h.res.statusCode).toBe(503);
    expect(JSON.parse(h.res.body)).toEqual({ detail: DEN_DOWN });
    expect(h.inner).not.toHaveBeenCalled();
  });
  it("啟動時 den 不在 → console.warn 一次", () => {
    const w = vi.spyOn(console, "warn").mockImplementation(() => {});
    denProxy(mkdir({}));
    expect(w).toHaveBeenCalledWith(DEN_DOWN);
    expect(w).toHaveBeenCalledTimes(1);
    w.mockRestore();
  });
});
