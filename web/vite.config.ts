import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { denProxy } from "./den-proxy";

export default defineConfig({
  plugins: [react()],
  // /api 代理到 den(同源,免 CORS);token 由 proxy 帶,瀏覽器碰不到。
  server: {
    proxy: {
      "/api": denProxy(),
    },
  },
});
