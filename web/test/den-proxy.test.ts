// @vitest-environment node
import { describe, it, expect, vi, afterEach } from "vitest";
import { createServer, request as httpRequest } from "node:http";
import type { AddressInfo } from "node:net";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { dataDir, denTarget, denHandler, denPlugin, DEN_DOWN } from "../den-proxy";

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

type Seen = { method?: string; url?: string; headers: Record<string, any>; body: string };

/** 真的 http server 兩端:fake den 回聲 + SSE;proxy 端掛 denHandler。 */
async function setup(dir: string) {
  const seen: Seen[] = [];
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  const den = createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", async () => {
      seen.push({ method: req.method, url: req.url, headers: req.headers, body });
      if (req.url === "/sse") {
        res.writeHead(200, { "Content-Type": "text/event-stream" });
        res.write("data: 1\n\n");
        await gate; // 測試確認收到第一幀後才放行第二幀
        res.end("data: 2\n\n");
        return;
      }
      res.writeHead(201, { "X-Den": "yes", "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: true }));
    });
  });
  await new Promise<void>((r) => den.listen(0, "127.0.0.1", r));
  const denPort = (den.address() as AddressInfo).port;
  writeFileSync(join(dir, "den.json"), JSON.stringify({ port: denPort }));
  const h = denHandler(dir);
  const web = createServer(h);
  await new Promise<void>((r) => web.listen(0, "127.0.0.1", r));
  const webPort = (web.address() as AddressInfo).port;
  const call = (path: string, headers: Record<string, string> = {}, method = "GET", body?: string) =>
    new Promise<{ status: number; headers: any; text: string }>((resolve, reject) => {
      const rq = httpRequest({ host: "127.0.0.1", port: webPort, path, method, headers }, (r) => {
        let text = "";
        r.on("data", (c) => (text += c));
        r.on("end", () => resolve({ status: r.statusCode!, headers: r.headers, text }));
      });
      rq.on("error", reject);
      rq.end(body);
    });
  const close = () => { den.closeAllConnections(); web.closeAllConnections(); den.close(); web.close(); };
  return { seen, call, release, webPort, denPort, close };
}
const mk = (files = full) => mkdir(files);
const self = (p: number) => `http://localhost:${p}`;

describe("denHandler", () => {
  let ctx: Awaited<ReturnType<typeof setup>>;
  afterEach(() => ctx?.close());

  it("同源 Origin:轉發 method/path/body,帶我們的 token,移除 origin,回應原樣", async () => {
    ctx = await setup(mk());
    const r = await ctx.call("/stories", { origin: self(ctx.webPort), "content-type": "application/json" }, "POST", '{"a":1}');
    expect(r.status).toBe(201);
    expect(r.headers["x-den"]).toBe("yes");
    expect(JSON.parse(r.text)).toEqual({ ok: true });
    const s = ctx.seen[0];
    expect([s.method, s.url, s.body]).toEqual(["POST", "/stories", '{"a":1}']);
    expect(s.headers.authorization).toBe("Bearer tok123");
    expect(s.headers.origin).toBeUndefined();
    expect(s.headers.host).toBe(`127.0.0.1:${ctx.denPort}`);
  });
  it("client 自帶的 authorization 被覆寫", async () => {
    ctx = await setup(mk());
    await ctx.call("/x", { origin: self(ctx.webPort), authorization: "Bearer evil" });
    expect(ctx.seen[0].headers.authorization).toBe("Bearer tok123");
  });
  it("Origin: null → 403", async () => {
    ctx = await setup(mk());
    expect((await ctx.call("/x", { origin: "null" })).status).toBe(403);
    expect(ctx.seen).toHaveLength(0);
  });
  it("外來 Origin → 403 不轉發", async () => {
    ctx = await setup(mk());
    expect((await ctx.call("/x", { origin: "http://evil.example" })).status).toBe(403);
    expect(ctx.seen).toHaveLength(0);
  });
  it("無 Origin + sec-fetch-site same-origin → 轉發", async () => {
    ctx = await setup(mk());
    expect((await ctx.call("/x", { "sec-fetch-site": "same-origin" })).status).toBe(201);
  });
  it("無 Origin 也無 sec-fetch-site → 403", async () => {
    ctx = await setup(mk());
    expect((await ctx.call("/x")).status).toBe(403);
  });
  it("無 Origin + sec-fetch-site cross-site → 403", async () => {
    ctx = await setup(mk());
    expect((await ctx.call("/x", { "sec-fetch-site": "cross-site" })).status).toBe(403);
  });
  it("每個請求重讀:den 換 port 後跟著走", async () => {
    const dir = mk();
    ctx = await setup(dir);
    const h = { "sec-fetch-site": "same-origin" };
    await ctx.call("/a", h);
    writeFileSync(join(dir, "den.json"), JSON.stringify({ port: 1 })); // 指到沒人聽的 port
    const r = await ctx.call("/b", h);
    expect(r.status).toBe(502);
    expect(r.text).not.toContain("tok123");
  });
  it("SSE 串流不緩衝:第一幀先到,第二幀才放行", async () => {
    ctx = await setup(mk());
    await new Promise<void>((resolve, reject) => {
      const rq = httpRequest({ host: "127.0.0.1", port: ctx.webPort, path: "/sse", headers: { "sec-fetch-site": "same-origin" } }, (r) => {
        let got = "";
        r.on("data", (c) => {
          got += c;
          if (got.includes("data: 1") && !got.includes("data: 2")) ctx.release(); // 此刻第二幀還沒送
          if (got.includes("data: 2")) resolve();
        });
      });
      rq.on("error", reject);
      rq.end();
    });
  });
});

describe("denHandler Host 檢查(DNS rebinding)", () => {
  let ctx: Awaited<ReturnType<typeof setup>>;
  afterEach(() => ctx?.close());

  it("Host evil.example + same-origin → 403,上游沒被打到", async () => {
    ctx = await setup(mk());
    const r = await ctx.call("/stories", { host: "evil.example:5173", "sec-fetch-site": "same-origin" });
    expect(r.status).toBe(403);
    expect(ctx.seen).toHaveLength(0);
  });
  it("Host evil.example + 看似合法的 Origin → 403", async () => {
    ctx = await setup(mk());
    const r = await ctx.call("/stories", { host: "evil.example:5173", origin: "http://localhost:5173" });
    expect(r.status).toBe(403);
    expect(ctx.seen).toHaveLength(0);
  });
  it("Host [::1]:5173 + Origin http://[::1]:5173 → 轉發", async () => {
    ctx = await setup(mk());
    const r = await ctx.call("/stories", { host: "[::1]:5173", origin: "http://[::1]:5173" });
    expect(r.status).toBe(201);
  });
  it("缺 Host → 403(直接餵 handler)", () => {
    const res: any = { setHeader: vi.fn(), end: vi.fn(), statusCode: 0 };
    denHandler(mkdir(full))({ headers: { "sec-fetch-site": "same-origin" }, url: "/x" } as any, res);
    expect(res.statusCode).toBe(403);
  });
});

describe("denHandler 無 den", () => {
  it("503 JSON", async () => {
    const web = createServer(denHandler(mkdir({})));
    await new Promise<void>((r) => web.listen(0, "127.0.0.1", r));
    const port = (web.address() as AddressInfo).port;
    const res = await fetch(`http://127.0.0.1:${port}/x`, { headers: { "sec-fetch-site": "same-origin" } });
    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ detail: DEN_DOWN });
    web.close();
  });
});

describe("denPlugin", () => {
  const fakeServer = (host: unknown) => {
    const use = vi.fn();
    return { use, server: { config: { server: { host } }, middlewares: { use } } as any };
  };
  it.each([undefined, "localhost", "127.0.0.1", "::1"])("host=%s → 掛 /api", (host) => {
    const f = fakeServer(host);
    (denPlugin(mkdir(full)).configureServer as any)(f.server);
    expect(f.use).toHaveBeenCalledWith("/api", expect.any(Function));
  });
  it.each(["0.0.0.0", "192.168.1.5", true])("host=%s → 不掛並警告", (host) => {
    const w = vi.spyOn(console, "warn").mockImplementation(() => {});
    const f = fakeServer(host);
    (denPlugin(mkdir(full)).configureServer as any)(f.server);
    expect(f.use).not.toHaveBeenCalled();
    expect(w).toHaveBeenCalled();
    w.mockRestore();
  });
  it("啟動時 den 不在 → console.warn 一次", () => {
    const w = vi.spyOn(console, "warn").mockImplementation(() => {});
    (denPlugin(mkdir({})).configureServer as any)(fakeServer(undefined).server);
    expect(w).toHaveBeenCalledWith(DEN_DOWN);
    expect(w).toHaveBeenCalledTimes(1);
    w.mockRestore();
  });
});
