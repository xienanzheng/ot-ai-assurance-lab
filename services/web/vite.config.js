import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL("./index.html", import.meta.url)),
        research: fileURLToPath(new URL("./research.html", import.meta.url)),
      },
    },
  },
  server: {
    port: 18773,
    strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:18780", ws: true },
    },
  },
});

