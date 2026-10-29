// web → den 的 backend-for-frontend:/api 代理到 den,由這裡帶 token、去 /api 前綴。
// 這裡是 web 這側的信任邊界:先驗 Origin(den 的 Origin 檢查不能被 proxy 洗掉),驗過才移除再轉給 den。
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import { request } from "node:http";
import type { Plugin } from "vite";

export const DEN_DOWN = "den 沒在跑:先 python -m den,或在 agent 裡用一次 hyenovel MCP";

/** 同 marrow/db.data_dir:HYENOVEL_DATA_DIR 直接用;否則 XDG_DATA_HOME 或 ~/.local/share,底下 hyenovel。 */
export function dataDir(env: NodeJS.ProcessEnv = process.env): string {
  if (env.HYENOVEL_DATA_DIR) return env.HYENOVEL_DATA_DIR;
  return join(env.XDG_DATA_HOME || join(homedir(), ".local", "share"), "hyenovel");
}

/** 讀 den.json(port)與 den.token;任一缺 → null。 */
export function denTarget(dir: string): { url: string; token: string } | null {
  try {
    const info = JSON.parse(readFileSync(join(dir, "den.json"), "utf8"));
    const token = readFileSync(join(dir, "den.token"), "utf8").trim();
    if (!info?.port || !token) return null;
    return { url: `http://127.0.0.1:${info.port}`, token };
  } catch {
    return null;
  }
}

const LOOPBACK = new Set(["localhost", "127.0.0.1", "::1"]);

/** 驗 Host 標頭(防 DNS rebinding;不倚賴 vite 的 hostCheck 中介層順序):
 *  hostname 必須是 loopback,回傳 host 的 port 部分(含冒號,可為空);否則 null。 */
function loopbackHost(req: IncomingMessage): { port: string } | null {
  const h = req.headers.host;
  if (!h) return null;
  const m = /^(\[[^\]]+\]|[^:]+)(?::(\d+))?$/.exec(h);
  if (!m) return null;
  const name = m[1].replace(/^\[|\]$/g, "").toLowerCase();
  return LOOPBACK.has(name) ? { port: m[2] ? `:${m[2]}` : "" } : null;
}

/** vite 自己的 origin:已驗過的 loopback Host 的 port,配 localhost / 127.0.0.1 / [::1]。 */
function allowedOrigins(port: string): string[] {
  return [`http://localhost${port}`, `http://127.0.0.1${port}`, `http://[::1]${port}`];
}

/** Origin 在白名單,或(沒有 Origin 且瀏覽器自報 same-origin)才放行;
 *  Origin: null、跨站、沒標頭的非瀏覽器請求一律擋。 */
function originOk(req: IncomingMessage, port: string): boolean {
  const origin = req.headers.origin;
  if (origin !== undefined) return allowedOrigins(port).includes(String(origin));
  return req.headers["sec-fetch-site"] === "same-origin";
}

function reply(res: ServerResponse, code: number, body: unknown) {
  res.statusCode = code;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(body));
}

/** 掛在 /api 底下的純 Node handler(connect 已去掉前綴,req.url 直接是 den 的路徑)。 */
export function denHandler(dir: string = dataDir()): (req: IncomingMessage, res: ServerResponse) => void {
  return (req, res) => {
    const host = loopbackHost(req);
    if (!host) return reply(res, 403, { detail: "Host 不被允許" });
    if (!originOk(req, host.port)) return reply(res, 403, { detail: "Origin 不被允許" });
    const t = denTarget(dir); // 每個請求重讀:den 可能換 port 重啟
    if (!t) return reply(res, 503, { detail: DEN_DOWN });
    const { origin: _o, host: _h, authorization: _a, ...rest } = req.headers;
    const port = Number(new URL(t.url).port);
    const up = request(
      { host: "127.0.0.1", port, path: req.url, method: req.method,
        headers: { ...rest, host: `127.0.0.1:${port}`, authorization: `Bearer ${t.token}` } },
      (ur) => {
        res.writeHead(ur.statusCode ?? 502, ur.headers);
        ur.pipe(res);
        res.on("close", () => ur.destroy()); // 瀏覽器斷線(SSE)就收掉上游
      },
    );
    up.on("error", () => {
      if (res.headersSent) res.destroy();
      else reply(res, 502, { detail: "連不上 den" });
    });
    req.pipe(up);
  };
}

/** vite plugin:/api → den。vite 綁到非 loopback 時不掛(token 不能借 proxy 外洩給區網)。 */
export function denPlugin(dir: string = dataDir()): Plugin {
  return {
    name: "hyenovel-den",
    configureServer(server) {
      const host = server.config.server.host;
      if (host !== undefined && host !== "localhost" && host !== "127.0.0.1" && host !== "::1") {
        console.warn("vite 綁在 loopback 之外,den proxy 已停用");
        return;
      }
      if (!denTarget(dir)) console.warn(DEN_DOWN);
      server.middlewares.use("/api", denHandler(dir));
    },
  };
}
