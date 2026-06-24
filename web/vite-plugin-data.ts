import { readFile } from "node:fs/promises";
import { resolve, normalize } from "node:path";
import type { Plugin } from "vite";

const STORIES = resolve(__dirname, "..", "stories");
const MIME: Record<string, string> = { ".json": "application/json", ".md": "text/markdown" };

export function dataServer(): Plugin {
  return {
    name: "hyenovel-data",
    configureServer(server) {
      server.middlewares.use("/data", async (req, res, next) => {
        try {
          const rel = normalize(decodeURIComponent((req.url || "/").split("?")[0]));
          if (rel.includes("..")) { res.statusCode = 403; return res.end("nope"); }
          const file = resolve(STORIES, "." + rel);
          if (!file.startsWith(STORIES)) { res.statusCode = 403; return res.end("nope"); }
          const ext = file.slice(file.lastIndexOf("."));
          const buf = await readFile(file);
          res.setHeader("Content-Type", MIME[ext] || "application/octet-stream");
          res.end(buf);
        } catch { next(); }
      });
    },
  };
}
