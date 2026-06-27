import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { dataServer } from "./vite-plugin-data";

export default defineConfig({
  plugins: [react(), dataServer()],
  // /data 由 dataServer 中介層出靜態檔;/api 代理到 FastAPI 後端(同源,免 CORS)。
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8787", changeOrigin: true },
    },
  },
});
