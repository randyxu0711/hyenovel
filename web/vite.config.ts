import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { dataServer } from "./vite-plugin-data";

export default defineConfig({ plugins: [react(), dataServer()] });
