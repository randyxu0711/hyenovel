import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { denPlugin } from "./den-proxy";

export default defineConfig({
  plugins: [react(), denPlugin()],
  // /api 由 denPlugin 中介層代理到 den(同源,免 CORS);token 由它帶,瀏覽器碰不到。
});
