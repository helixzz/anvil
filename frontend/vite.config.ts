import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { readFileSync } from "node:fs";

const pkg = JSON.parse(readFileSync(path.resolve(__dirname, "package.json"), "utf-8"));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  define: {
    __ANVIL_WEB_VERSION__: JSON.stringify(pkg.version),
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_BASE || "http://localhost:8080",
        changeOrigin: true,
      },
      "/ws": {
        target: (process.env.VITE_API_BASE || "http://localhost:8080").replace(
          /^http/,
          "ws",
        ),
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("echarts") || id.includes("zrender")) return "vendor-echarts";
          if (id.includes("react-dom") || id.includes("scheduler")) return "vendor-react";
          if (id.includes("/react/")) return "vendor-react";
          if (id.includes("@tanstack")) return "vendor-query";
          if (id.includes("i18next")) return "vendor-i18n";
          if (id.includes("react-router")) return "vendor-router";
          return "vendor";
        },
      },
    },
  },
});
