import { defineConfig } from "vite";
import solid from "vite-plugin-solid";

const apiProxyTarget = process.env.AGENT_WEB_API_PROXY || "http://127.0.0.1:8020";
const apiProxy = {
  "/api": { target: apiProxyTarget, changeOrigin: true },
  "/health": { target: apiProxyTarget, changeOrigin: true },
};

export default defineConfig({
  base: "/ui/",
  plugins: [solid()],
  server: {
    proxy: apiProxy,
  },
  preview: {
    proxy: apiProxy,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false
  }
});
