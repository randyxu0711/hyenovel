// web → den 的 backend-for-frontend:/api 代理到 den,由這裡帶 token、去 /api 前綴。
// 這裡是 web 這側的信任邊界:先驗 Origin(den 的 Origin 檢查不能被 proxy 洗掉),驗過才移除再轉給 den。
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { ProxyOptions } from "vite";

export const DEN_DOWN = "den 沒在跑:先 python -m den,或在 agent 裡用一次 hyenovel MCP";

/** 同 marrow/db.data_dir:XDG_DATA_HOME 或 ~/.local/share,底下 hyenovel。 */
export function dataDir(env: NodeJS.ProcessEnv = process.env): string {
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

/** vite 自己的 origin:Host 標頭的 port,配 localhost / 127.0.0.1。 */
function allowedOrigins(req: IncomingMessage): string[] {
  const port = String(req.headers.host ?? "").split(":")[1];
  const suffix = port ? `:${port}` : "";
  return [`http://localhost${suffix}`, `http://127.0.0.1${suffix}`];
}

function reply(res: ServerResponse, code: number, body: unknown) {
  res.statusCode = code;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(body));
}

export function denProxy(dir: string = dataDir()): ProxyOptions {
  if (!denTarget(dir)) console.warn(DEN_DOWN);
  return {
    target: "http://127.0.0.1:1", // 佔位;每個請求在 configure 包的 web() 重讀 den.json 覆寫
    changeOrigin: true,
    rewrite: (p) => p.replace(/^\/api/, ""),
    configure(proxy) {
      const web = proxy.web.bind(proxy) as (...a: any[]) => unknown;
      (proxy as any).web = (req: IncomingMessage, res: ServerResponse, opts: any = {}, cb?: any) => {
        const origin = req.headers.origin;
        if (origin !== undefined && !allowedOrigins(req).includes(String(origin))) {
          return reply(res, 403, { detail: "Origin 不被允許" });
        }
        const t = denTarget(dir);
        if (!t) return reply(res, 503, { detail: DEN_DOWN });
        delete req.headers.origin;
        return web(req, res, { ...opts, target: t.url, headers: { ...opts.headers, Authorization: `Bearer ${t.token}` } }, cb);
      };
    },
  };
}
